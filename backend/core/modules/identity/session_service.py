"""id.agri.in web-session lifecycle (D09.A/C) - no HTTP here.

The sid is a 256-bit random token; sessions_web stores SHA-256(sid) only, the
plaintext exists exactly once in create_web_session's return value (it goes
straight into the Set-Cookie header). Resolution re-checks user status on
every request, so suspension is an instant deny, not an eventual one.

Functions take the caller's AsyncSession and flush but never commit.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import SessionRefresh, SessionWeb
from modules.identity.oauth_service import hash_code, load_token_subject
from modules.identity.session_limits import WEB_SESSION_TTL_SECONDS
from shared.telemetry import get_logger

logger = get_logger(__name__)


FINGERPRINT_CHARS = 32


def _hash_fingerprint(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()[:FINGERPRINT_CHARS]


def device_fingerprint(user_agent: str | None, platform: str | None = None) -> str:
    """Privacy-light device binding: the user agent, hashed.

    Deliberately coarse - it distinguishes "my laptop" from "a stolen token
    replayed elsewhere", not one user from another. 32 hex chars keep rows
    compact; collision resistance at that scope is ample.

    WHY `platform` IS ACCEPTED AND IGNORED. This used to hash
    `UA|sec-ch-ua-platform`. That hint is a client hint, and a client hint is
    not guaranteed on every request: Chrome omits it on some paths, and the
    BFF can only forward what it actually received. So the SAME browser
    produced two fingerprints depending on which route minted the credential,
    which showed up as two rows on /devices that drifted apart on every visit,
    and made this-device logout (revoke_families_for_device) silently miss
    whichever half the current request did not match. The hint added almost no
    binding strength over the UA it accompanies - it is derived from the same
    self-reported browser identity - so the honest fix is to drop it rather
    than to chase it onto every route. The parameter stays so call sites (and
    legacy_fingerprints below) keep one shared signature.
    """
    return _hash_fingerprint(user_agent or "")


def legacy_fingerprints(user_agent: str | None, platform: str | None) -> tuple[str, ...]:
    """Pre-fix hashes this same device could be stored under.

    Rows minted before the change above hash `UA|platform`, with `platform`
    either present or empty depending on the route. Rotation checks these so
    an existing session reads as the same device rather than as token theft -
    without them, shipping the fix would revoke every live refresh family in
    the system and write a device_mismatch audit line for each one.
    """
    return tuple(
        dict.fromkeys(
            (
                _hash_fingerprint(f"{user_agent or ''}|{platform or ''}"),
                _hash_fingerprint(f"{user_agent or ''}|"),
            )
        )
    )


@dataclass(frozen=True)
class WebPrincipal:
    """The resolved identity routers act on. Internal-only shape - response
    models re-expose agri_id and stringified session ids only. session_id is
    None for bearer-token principals (D11): no web session exists to revoke."""

    user_id: uuid.UUID
    agri_id: str
    roles: tuple[str, ...]
    session_id: uuid.UUID | None
    fingerprint: str | None


async def create_web_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    fingerprint: str,
    ip: str | None,
    device_label: str | None = None,
    device_kind: str | None = None,
) -> str:
    """Mint a session and return the plaintext sid exactly once.

    Fixation hardening: callers ALWAYS get a fresh sid at login - there is no
    code path that adopts or upgrades a pre-login identifier.

    This device's PREVIOUS session is superseded here. A browser holds exactly
    one agri_sid, so the old row became unreachable the instant this one was
    minted; leaving it live for the rest of its TTL only added a row per login
    to /devices. Scoped to this user AND this fingerprint - a shared computer
    must not let one person's login end another's, and other devices are never
    touched. Note this does not weaken the fixation rule above: the new sid is
    still freshly generated, and nothing is carried over from the old row.
    """
    if fingerprint:
        await session.execute(
            update(SessionWeb)
            .where(
                SessionWeb.user_id == user_id,
                SessionWeb.device_fingerprint == fingerprint,
                SessionWeb.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
    sid = secrets.token_urlsafe(32)
    session.add(
        SessionWeb(
            user_id=user_id,
            sid_hash=hash_code(sid),
            device_fingerprint=fingerprint,
            device_label=device_label,
            device_kind=device_kind,
            ip=ip,
            expires_at=datetime.now(UTC) + timedelta(seconds=WEB_SESSION_TTL_SECONDS),
        )
    )
    await session.flush()
    logger.info("session.web.created", extra={"extra_fields": {"user": str(user_id)}})
    return sid


async def resolve_web_session(session: AsyncSession, sid: str) -> WebPrincipal | None:
    """None for unknown, expired, revoked, or non-active-user sessions - the
    four cases are indistinguishable to callers (and to attackers)."""
    now = datetime.now(UTC)
    row = await session.scalar(
        select(SessionWeb).where(
            SessionWeb.sid_hash == hash_code(sid),
            SessionWeb.revoked_at.is_(None),
            SessionWeb.expires_at > now,
        )
    )
    if row is None:
        return None
    subject = await load_token_subject(session, row.user_id)
    if subject is None:  # suspended or gone: instant deny
        return None
    row.last_seen_at = now
    await session.flush()
    return WebPrincipal(
        user_id=subject.user_id,
        agri_id=subject.agri_id,
        roles=subject.roles,
        session_id=row.id,
        fingerprint=row.device_fingerprint,
    )


async def revoke_web_session(
    session: AsyncSession, *, session_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Revoke one session, only if it belongs to user_id (ownership in the
    WHERE clause, not in caller logic)."""
    row = await session.scalar(
        update(SessionWeb)
        .where(
            SessionWeb.id == session_id,
            SessionWeb.user_id == user_id,
            SessionWeb.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
        .returning(SessionWeb.id)
    )
    return row is not None


async def revoke_everything(session: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    """Logout-everywhere: every web session and every refresh row, two bulk
    UPDATEs inside the caller's single transaction (one request cycle, the
    non-negotiable a test pins)."""
    now = datetime.now(UTC)
    web_ids = (
        await session.scalars(
            update(SessionWeb)
            .where(SessionWeb.user_id == user_id, SessionWeb.revoked_at.is_(None))
            .values(revoked_at=now)
            .returning(SessionWeb.id)
        )
    ).all()
    refresh_ids = (
        await session.scalars(
            update(SessionRefresh)
            .where(SessionRefresh.user_id == user_id, SessionRefresh.revoked_at.is_(None))
            .values(revoked_at=now)
            .returning(SessionRefresh.id)
        )
    ).all()
    logger.warning(
        "session.logout_everywhere",
        extra={
            "extra_fields": {
                "user": str(user_id),
                "web_revoked": len(web_ids),
                "refresh_revoked": len(refresh_ids),
            }
        },
    )
    return len(web_ids), len(refresh_ids)
