"""Rotating refresh tokens (D09.B) - no HTTP, no authlib here.

Lifecycle invariants (the ones the reuse test pins):
- sessions_refresh stores SHA-256(token) only; plaintext exists exactly once,
  in RefreshRotation.token, and goes straight into the /token response body.
- family_id is the ROOT row's id, copied to every rotation descendant. One
  bulk UPDATE on family_id revokes an entire lineage.
- Rotation is an atomic UPDATE .. WHERE revoked_at IS NULL .. RETURNING: two
  racing rotations can never both win. The loser's presented token now hashes
  to a REVOKED row, which is exactly the reuse signature.
- Reuse of ANY revoked row's token (rotated-away or logged-out) revokes the
  whole family and logs an audit line - the token was seen by two parties, so
  every credential derived from it is presumed stolen.
- Device binding is strict: a fingerprint mismatch is treated as theft, not
  drift - family revoked. A browser upgrade changes the fingerprint and logs
  that device out; acceptable v1 cost, decided in the D09 plan. The ONE
  exception is a row still stored under a pre-UA-only fingerprint format
  (session_service.legacy_fingerprints): that is the same device described
  differently, so it is restamped rather than revoked.
- One live family per (user, client, device): a fresh code exchange supersedes
  this device's previous family for that client, because the browser can no
  longer reach the old one anyway.
- Rotation happens on the ATTEMPT, before authlib judges the request
  (burn-on-attempt, mirrors D08 codes and D07 OTP burn semantics).

Functions take the caller's AsyncSession and flush but never commit.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import uuid6
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import OAuthClient, SessionRefresh
from modules.identity.oauth_service import TokenSubject, hash_code, load_token_subject
from modules.identity.session_limits import REFRESH_TOKEN_TTL_SECONDS
from shared.telemetry import get_logger

logger = get_logger(__name__)


class RefreshInvalidError(Exception):
    """Unknown, expired, foreign-client, device-mismatched, or dead-user
    token. Callers surface every case identically (invalid_grant)."""


class RefreshReuseError(RefreshInvalidError):
    """A revoked token was presented: theft signature. The family is already
    revoked by the time this raises."""


@dataclass(frozen=True)
class RefreshRotation:
    token: str
    row_id: uuid.UUID
    family_id: uuid.UUID
    subject: TokenSubject


def _new_row(
    *,
    user_id: uuid.UUID,
    client_row_id: uuid.UUID,
    family_id: uuid.UUID | None,
    fingerprint: str | None,
    device_label: str | None,
    device_kind: str | None,
    ip: str | None,
    rotated_from: uuid.UUID | None,
) -> tuple[str, SessionRefresh]:
    token = secrets.token_urlsafe(32)
    # the PK default fires at flush, so a root row (family_id is None) needs
    # its id up front to anchor its own family
    row_id = uuid6.uuid7()
    row = SessionRefresh(
        id=row_id,
        user_id=user_id,
        token_hash=hash_code(token),
        client_id=client_row_id,
        device_fingerprint=fingerprint,
        device_label=device_label,
        device_kind=device_kind,
        ip=ip,
        expires_at=datetime.now(UTC) + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
        rotated_from=rotated_from,
        family_id=family_id if family_id is not None else row_id,
    )
    return token, row


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> int:
    revoked = (
        await session.scalars(
            update(SessionRefresh)
            .where(SessionRefresh.family_id == family_id, SessionRefresh.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
            .returning(SessionRefresh.id)
        )
    ).all()
    return len(revoked)


async def revoke_by_token(session: AsyncSession, *, token: str, client: OAuthClient) -> bool:
    """RFC 7009-style revocation: retire the whole family this token belongs
    to. Scoped to the presenting client - a foreign client's guess is a no-op,
    and callers never learn whether the token existed."""
    row = await session.scalar(
        select(SessionRefresh).where(
            SessionRefresh.token_hash == hash_code(token),
            SessionRefresh.client_id == client.id,
        )
    )
    if row is None:
        return False
    await revoke_family(session, row.family_id)
    return True


async def revoke_families_for_device(
    session: AsyncSession, *, user_id: uuid.UUID, fingerprint: str
) -> int:
    """This-device logout: kill every refresh row minted from this device."""
    revoked = (
        await session.scalars(
            update(SessionRefresh)
            .where(
                SessionRefresh.user_id == user_id,
                SessionRefresh.device_fingerprint == fingerprint,
                SessionRefresh.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
            .returning(SessionRefresh.id)
        )
    ).all()
    return len(revoked)


async def issue_refresh_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    client: OAuthClient,
    fingerprint: str | None,
    ip: str | None,
    device_label: str | None = None,
    device_kind: str | None = None,
) -> RefreshRotation:
    """Start a new family (the code-exchange mint point).

    Re-authenticating supersedes this device's previous family for THIS client.
    A browser holds one cookie jar per app, so the moment a new family is
    minted the old one is unreachable - leaving it live for its full TTL only
    grew /devices by a row per SSO round trip and left a valid refresh token
    behind that nobody could present. Scoping is deliberate: same user, same
    client, same device. Other apps and other devices are untouched.

    Known blast radius: two browser PROFILES on one machine share a UA and so
    share a fingerprint, and signing into the second supersedes the first for
    that app. That is the same device granularity revoke_families_for_device
    (this-device logout) has always had, not a new rule.
    """
    subject = await load_token_subject(session, user_id)
    if subject is None:
        raise RefreshInvalidError("subject not eligible")
    if fingerprint is not None:
        # None means we could not identify the device at all - superseding on
        # that would let one unidentifiable client evict every other.
        superseded = (
            await session.scalars(
                update(SessionRefresh)
                .where(
                    SessionRefresh.user_id == user_id,
                    SessionRefresh.client_id == client.id,
                    SessionRefresh.device_fingerprint == fingerprint,
                    SessionRefresh.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
                .returning(SessionRefresh.id)
            )
        ).all()
        if superseded:
            logger.info(
                "refresh.family.superseded",
                extra={"extra_fields": {"client": client.client_id, "rows": len(superseded)}},
            )
    token, row = _new_row(
        user_id=user_id,
        client_row_id=client.id,
        family_id=None,
        fingerprint=fingerprint,
        device_label=device_label,
        device_kind=device_kind,
        ip=ip,
        rotated_from=None,
    )
    session.add(row)
    await session.flush()
    logger.info(
        "refresh.family.issued",
        extra={"extra_fields": {"family": str(row.family_id), "client": client.client_id}},
    )
    return RefreshRotation(token=token, row_id=row.id, family_id=row.family_id, subject=subject)


async def rotate_refresh_token(
    session: AsyncSession,
    *,
    token: str,
    client: OAuthClient,
    fingerprint: str | None,
    legacy: tuple[str, ...] = (),
) -> RefreshRotation:
    """Atomically retire the presented token and mint its successor.

    `legacy` carries the hashes this same device would have been stored under
    before the fingerprint format changed (session_service.legacy_fingerprints).
    A row matching one of those is the same device, not a thief - it is
    upgraded in place rather than revoked.

    Order matters and every branch is deliberate:
    1. Atomic claim (UPDATE .. revoked_at IS NULL .. RETURNING) scoped to this
       client. Success means WE retired a live token just now.
    2. Claim failed but the hash exists for this client -> the token was
       already retired: REUSE. Revoke the family, audit, raise.
    3. Claim succeeded but the row was already past expiry -> plain invalid
       (a hoarded-not-stolen token; no family damage).
    4. Fingerprint mismatch, and not a known legacy form of THIS device ->
       theft signal: revoke family, audit, raise.
    5. Suspended/missing user -> revoke family, raise (instant deny).
    6. Mint successor: same family_id, rotated_from=old row.
    """
    now = datetime.now(UTC)
    presented_hash = hash_code(token)
    row = await session.scalar(
        update(SessionRefresh)
        .where(
            SessionRefresh.token_hash == presented_hash,
            SessionRefresh.client_id == client.id,
            SessionRefresh.revoked_at.is_(None),
        )
        .values(revoked_at=now, last_used_at=now)
        .returning(SessionRefresh)
    )
    if row is None:
        stale = await session.scalar(
            select(SessionRefresh).where(
                SessionRefresh.token_hash == presented_hash,
                SessionRefresh.client_id == client.id,
            )
        )
        if stale is not None:
            revoked = await revoke_family(session, stale.family_id)
            logger.warning(
                "refresh.reuse.family_revoked",
                extra={
                    "extra_fields": {
                        "family": str(stale.family_id),
                        "client": client.client_id,
                        "revoked_rows": revoked,
                    }
                },
            )
            raise RefreshReuseError("rotated token replayed")
        raise RefreshInvalidError("unknown token")
    if row.expires_at <= now:
        raise RefreshInvalidError("expired token")
    if fingerprint != row.device_fingerprint:
        if row.device_fingerprint is not None and row.device_fingerprint in legacy:
            # Same device, pre-fix hash format. Restamp the WHOLE family, not
            # just the row we are about to retire: revoke_families_for_device
            # matches on this column, so a lineage that is half old-format and
            # half new would only ever be half logged out.
            await session.execute(
                update(SessionRefresh)
                .where(SessionRefresh.family_id == row.family_id)
                .values(device_fingerprint=fingerprint)
            )
            row.device_fingerprint = fingerprint
            logger.info(
                "refresh.fingerprint.upgraded",
                extra={
                    "extra_fields": {
                        "family": str(row.family_id),
                        "client": client.client_id,
                    }
                },
            )
        else:
            revoked = await revoke_family(session, row.family_id)
            logger.warning(
                "refresh.device_mismatch.family_revoked",
                extra={
                    "extra_fields": {
                        "family": str(row.family_id),
                        "client": client.client_id,
                        "revoked_rows": revoked,
                    }
                },
            )
            raise RefreshInvalidError("device mismatch")
    subject = await load_token_subject(session, row.user_id)
    if subject is None:
        await revoke_family(session, row.family_id)
        raise RefreshInvalidError("subject not eligible")
    new_token, new_row = _new_row(
        user_id=row.user_id,
        client_row_id=row.client_id,
        family_id=row.family_id,
        fingerprint=row.device_fingerprint,
        device_label=row.device_label,
        # a rotation is the SAME device; carry the description forward rather
        # than re-deriving it from whatever UA presented the refresh token
        device_kind=row.device_kind,
        ip=row.ip,
        rotated_from=row.id,
    )
    session.add(new_row)
    await session.flush()
    return RefreshRotation(
        token=new_token, row_id=new_row.id, family_id=new_row.family_id, subject=subject
    )
