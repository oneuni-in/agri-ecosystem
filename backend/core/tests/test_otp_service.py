"""OTP issue/verify services (D07.A/B): happy path, hash-at-rest, reissue
invalidation, expiry, 3-attempt burn, purpose scoping, and single-use proof."""

from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import OtpRequest
from modules.identity.otp_drivers import MockDriver
from modules.identity.otp_limits import OTP_MAX_ATTEMPTS
from modules.identity.otp_service import (
    OtpVerifyError,
    consume_otp_proof,
    issue_otp,
    verify_otp,
)
from modules.identity.phone import PhoneError

PHONE = "+919876543210"


async def clear_cooldown(redis: Redis, phone: str = PHONE) -> None:
    await redis.delete(f"otp:cd:{phone}")


def sent_code(phone: str = PHONE) -> str:
    code = MockDriver.last_code(phone)
    assert code is not None
    return code


async def test_issue_and_verify_happy_path(db_session: AsyncSession, otp_redis: Redis) -> None:
    await issue_otp(db_session, phone=PHONE, purpose="login")
    proof = await verify_otp(db_session, phone=PHONE, purpose="login", code=sent_code())
    assert isinstance(proof, str) and len(proof) >= 32

    consumed = await consume_otp_proof(proof)
    assert consumed == (PHONE, "login")
    # single use: a second redemption gets nothing
    assert await consume_otp_proof(proof) is None


async def test_issue_normalizes_bare_indian_mobile(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    await issue_otp(db_session, phone="98765 43210", purpose="login")
    assert MockDriver.last_code(PHONE) is not None


async def test_issue_rejects_malformed_phone(db_session: AsyncSession, otp_redis: Redis) -> None:
    with pytest.raises(PhoneError):
        await issue_otp(db_session, phone="12345", purpose="login")


async def test_code_is_hashed_at_rest(db_session: AsyncSession, otp_redis: Redis) -> None:
    await issue_otp(db_session, phone=PHONE, purpose="login")
    row = await db_session.scalar(select(OtpRequest).where(OtpRequest.phone == PHONE))
    assert row is not None
    code = sent_code()
    assert code not in row.code_hash
    assert len(row.code_hash) == 64  # HMAC-SHA256 hex, never the code


async def test_reissue_invalidates_prior_code(db_session: AsyncSession, otp_redis: Redis) -> None:
    await issue_otp(db_session, phone=PHONE, purpose="login")
    first_code = sent_code()
    await clear_cooldown(otp_redis)
    await issue_otp(db_session, phone=PHONE, purpose="login")
    second_code = sent_code()

    with pytest.raises(OtpVerifyError):
        await verify_otp(db_session, phone=PHONE, purpose="login", code=first_code)
    if first_code != second_code:  # 1-in-10^6 collision would make this a no-op
        proof = await verify_otp(db_session, phone=PHONE, purpose="login", code=second_code)
        assert proof


async def test_expired_code_fails(db_session: AsyncSession, otp_redis: Redis) -> None:
    await issue_otp(db_session, phone=PHONE, purpose="login")
    await db_session.execute(
        update(OtpRequest)
        .where(OtpRequest.phone == PHONE)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    with pytest.raises(OtpVerifyError):
        await verify_otp(db_session, phone=PHONE, purpose="login", code=sent_code())


async def test_three_wrong_attempts_burn_the_code(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    await issue_otp(db_session, phone=PHONE, purpose="login")
    code = sent_code()
    wrong = "000000" if code != "000000" else "000001"
    for _ in range(OTP_MAX_ATTEMPTS):
        with pytest.raises(OtpVerifyError):
            await verify_otp(db_session, phone=PHONE, purpose="login", code=wrong)
    # burned: even the correct code is dead now
    with pytest.raises(OtpVerifyError):
        await verify_otp(db_session, phone=PHONE, purpose="login", code=code)


async def test_correct_code_on_final_attempt_succeeds(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    await issue_otp(db_session, phone=PHONE, purpose="login")
    code = sent_code()
    wrong = "000000" if code != "000000" else "000001"
    for _ in range(OTP_MAX_ATTEMPTS - 1):
        with pytest.raises(OtpVerifyError):
            await verify_otp(db_session, phone=PHONE, purpose="login", code=wrong)
    assert await verify_otp(db_session, phone=PHONE, purpose="login", code=code)


async def test_code_is_purpose_scoped(db_session: AsyncSession, otp_redis: Redis) -> None:
    await issue_otp(db_session, phone=PHONE, purpose="login")
    with pytest.raises(OtpVerifyError):
        await verify_otp(db_session, phone=PHONE, purpose="sensitive_action", code=sent_code())


async def test_verified_code_cannot_be_replayed(db_session: AsyncSession, otp_redis: Redis) -> None:
    await issue_otp(db_session, phone=PHONE, purpose="login")
    code = sent_code()
    await verify_otp(db_session, phone=PHONE, purpose="login", code=code)
    with pytest.raises(OtpVerifyError):
        await verify_otp(db_session, phone=PHONE, purpose="login", code=code)


async def test_verify_with_no_code_ever_issued_fails_identically(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    # unknown phone and wrong code raise the same exception type with no
    # distinguishing payload - the enumeration guarantee at the service level
    with pytest.raises(OtpVerifyError):
        await verify_otp(db_session, phone="+919876500000", purpose="login", code="123456")


async def test_consume_unknown_proof_returns_none(otp_redis: Redis) -> None:
    assert await consume_otp_proof("no-such-token") is None
