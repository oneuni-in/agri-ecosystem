"""OTP issue/verify services (D07.A/B) - no HTTP here.

Lifecycle invariants:
- A row in identity.otp_requests is *active* iff expires_at > now(); reissue,
  successful consumption, and attempt-burn all invalidate by setting
  expires_at = now(). No plaintext code column exists anywhere.
- code_hash = HMAC-SHA256(otp_pepper, "phone:purpose:code"): the pepper lives
  only in the environment, so a DB dump alone cannot offline-brute the 10^6
  code space. Comparison is hmac.compare_digest, and the no-active-code path
  compares against a dummy digest so unknown phones cost the same time.
- Verify hands back a single-use otp_proof (Redis, GETDEL) consumed by the
  D08/D09 login flow - never a session or JWT.

Functions take the caller's AsyncSession and flush but never commit.
"""

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity import otp_throttle
from modules.identity.models import OtpRequest
from modules.identity.otp_drivers import get_sms_driver
from modules.identity.otp_limits import (
    OTP_CODE_LENGTH,
    OTP_MAX_ATTEMPTS,
    OTP_PROOF_TTL_SECONDS,
    OTP_TTL_SECONDS,
)
from modules.identity.phone import normalize_phone
from settings import get_settings
from shared.cache import get_redis
from shared.metrics import OTP_ISSUED, OTP_VERIFIED
from shared.telemetry import get_logger

logger = get_logger(__name__)

OtpPurpose = Literal["login", "verify_email", "sensitive_action"]


class OtpVerifyError(Exception):
    """One failure for every cause (wrong/expired/burned/absent): callers must
    not be able to distinguish them (phone enumeration)."""


def hash_code(phone: str, purpose: str, code: str) -> str:
    key = get_settings().otp_pepper.encode()
    return hmac.new(key, f"{phone}:{purpose}:{code}".encode(), hashlib.sha256).hexdigest()


def _proof_key(token: str) -> str:
    # the token is the credential: store only its hash so a Redis dump does
    # not yield usable proofs
    return f"otp:proof:{hashlib.sha256(token.encode()).hexdigest()}"


async def issue_otp(
    session: AsyncSession,
    *,
    phone: str,
    purpose: OtpPurpose,
    ip: str | None = None,
    device_fingerprint: str | None = None,
) -> None:
    """Issue a fresh code for phone+purpose; any prior active code dies now.

    Raises PhoneError (bad input) or OtpRateLimited (throttled). Deliberately
    never looks up whether the phone belongs to a user - issuing must behave
    identically for registered and unknown numbers.
    """
    normalized = normalize_phone(phone)
    await otp_throttle.assert_issue_allowed(normalized, ip, device_fingerprint)
    now = datetime.now(UTC)
    await session.execute(
        update(OtpRequest)
        .where(
            OtpRequest.phone == normalized,
            OtpRequest.purpose == purpose,
            OtpRequest.expires_at > now,
        )
        .values(expires_at=now)
    )
    code = f"{secrets.randbelow(10**OTP_CODE_LENGTH):0{OTP_CODE_LENGTH}d}"
    session.add(
        OtpRequest(
            phone=normalized,
            code_hash=hash_code(normalized, purpose, code),
            purpose=purpose,
            expires_at=now + timedelta(seconds=OTP_TTL_SECONDS),
            ip=ip,
            device_fingerprint=device_fingerprint,
        )
    )
    await session.flush()
    await otp_throttle.register_issue(normalized, ip)
    await get_sms_driver().send_otp(normalized, code, purpose)
    OTP_ISSUED.labels(purpose, get_settings().sms_provider).inc()


async def verify_otp(
    session: AsyncSession,
    *,
    phone: str,
    purpose: OtpPurpose,
    code: str,
    ip: str | None = None,
) -> str:
    """Check a code; on success consume it and return a single-use otp_proof.

    Raises OtpRateLimited (verify budget) or OtpVerifyError (one identical
    failure for wrong code, expired, burned, or no code at all).
    """
    normalized = normalize_phone(phone)
    await otp_throttle.assert_verify_allowed(ip)
    now = datetime.now(UTC)
    row = await session.scalar(
        select(OtpRequest)
        .where(
            OtpRequest.phone == normalized,
            OtpRequest.purpose == purpose,
            OtpRequest.expires_at > now,
        )
        .order_by(OtpRequest.created_at.desc())
        .limit(1)
    )
    supplied_hash = hash_code(normalized, purpose, code)
    if row is None:
        # burn the same compare time as the real path (timing enumeration)
        hmac.compare_digest(supplied_hash, hash_code(normalized, purpose, "!missing!"))
        OTP_VERIFIED.labels("no_active_code").inc()
        raise OtpVerifyError
    row.attempts += 1
    if not hmac.compare_digest(supplied_hash, row.code_hash):
        if row.attempts >= OTP_MAX_ATTEMPTS:
            row.expires_at = now  # burned: even the right code is dead now
            OTP_VERIFIED.labels("burned").inc()
        else:
            OTP_VERIFIED.labels("wrong_code").inc()
        await session.flush()
        raise OtpVerifyError
    row.expires_at = now  # consumed: single successful use
    await session.flush()
    token = secrets.token_urlsafe(32)
    await get_redis().set(
        _proof_key(token),
        json.dumps({"phone": normalized, "purpose": purpose}),
        ex=OTP_PROOF_TTL_SECONDS,
    )
    OTP_VERIFIED.labels("ok").inc()
    return token


async def consume_otp_proof(token: str) -> tuple[str, str] | None:
    """Single-use redemption for D08/D09: (phone, purpose), or None if the
    proof is unknown, expired, or already consumed (GETDEL is atomic)."""
    raw = await get_redis().getdel(_proof_key(token))
    if raw is None:
        return None
    payload = json.loads(raw)
    return payload["phone"], payload["purpose"]
