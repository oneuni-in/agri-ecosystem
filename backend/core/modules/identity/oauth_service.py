"""OAuth2 authorization-code persistence (D08.B) - no HTTP, no authlib here.

Lifecycle invariants:
- oauth_codes stores SHA-256(code) only; the plaintext code exists exactly
  once, in the return value of create_authorization_code. (No pepper needed:
  codes are 256-bit random tokens, not a brute-forceable 10^6 space.)
- A code is exchangeable iff consumed_at IS NULL and expires_at > now(), and
  only by the client it was minted for. consume_authorization_code flips
  consumed_at atomically (UPDATE .. WHERE consumed_at IS NULL .. RETURNING),
  so two racing /token calls can never both win - the reuse test rides this.
- Consumption happens on the first exchange ATTEMPT: a code burned by a
  failed PKCE check stays burned (interception hardening, mirrors D07's
  burn-on-failure).

Functions take the caller's AsyncSession and flush but never commit.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import OAuthClient, OAuthCode, Profile, Role, User, UserRole
from modules.identity.oauth_limits import AUTH_CODE_TTL_SECONDS


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


async def get_client(session: AsyncSession, client_id: str) -> OAuthClient | None:
    client: OAuthClient | None = await session.scalar(
        select(OAuthClient).where(OAuthClient.client_id == client_id)
    )
    return client


async def create_authorization_code(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    client: OAuthClient,
    redirect_uri: str,
    code_challenge: str,
    scope: str = "",
) -> str:
    """Mint a one-time code (60s TTL) and return its plaintext exactly once.

    Callers (D09 login flow, tests) validate redirect_uri and the S256
    challenge BEFORE minting - this function records, it does not judge.
    """
    code = secrets.token_urlsafe(32)
    session.add(
        OAuthCode(
            code_hash=hash_code(code),
            client_id=client.id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method="S256",
            scope=scope,
            expires_at=datetime.now(UTC) + timedelta(seconds=AUTH_CODE_TTL_SECONDS),
        )
    )
    await session.flush()
    return code


async def consume_authorization_code(
    session: AsyncSession, *, code: str, client: OAuthClient
) -> OAuthCode | None:
    """Atomically burn-and-fetch a code for this client.

    Returns None identically for reused, expired, foreign-client, and
    never-issued codes - callers surface all four as invalid_grant.
    """
    now = datetime.now(UTC)
    return await session.scalar(
        update(OAuthCode)
        .where(
            OAuthCode.code_hash == hash_code(code),
            OAuthCode.client_id == client.id,
            OAuthCode.consumed_at.is_(None),
            OAuthCode.expires_at > now,
        )
        .values(consumed_at=now)
        .returning(OAuthCode)
    )


@dataclass(frozen=True)
class TokenSubject:
    user_id: uuid.UUID
    agri_id: str
    roles: tuple[str, ...]
    name: str | None = None


async def load_token_subject(session: AsyncSession, user_id: uuid.UUID) -> TokenSubject | None:
    """Claims material for the access token. None for suspended or missing
    users (soft-deleted ones are filtered by the D03 mixin) - deny at mint."""
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None or user.status != "active":
        return None
    roles = await session.scalars(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    name = await session.scalar(select(Profile.name).where(Profile.user_id == user_id))
    return TokenSubject(
        user_id=user.id, agri_id=user.agri_id, roles=tuple(sorted(roles)), name=name
    )
