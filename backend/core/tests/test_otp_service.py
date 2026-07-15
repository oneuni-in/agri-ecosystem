"""OTP issue/verify services (D07.A/B): happy path, hash-at-rest, reissue
invalidation, expiry, 3-attempt burn, purpose scoping, and single-use proof."""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from modules.identity.models import OtpRequest
from modules.identity.otp_drivers import MockDriver
from modules.identity.otp_limits import OTP_MAX_ATTEMPTS
from modules.identity.otp_service import (
    OtpPurpose,
    OtpVerifyError,
    consume_otp_proof,
    hash_code,
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


# --- D14 Task 14: verify_otp lost-update race (Critical, sprint1-audit.md A6) --
#
# The `db_session` fixture above is a single connection wrapped in one outer
# transaction with savepoints (conftest.py) - every "concurrent" query on it
# would actually serialize through Python's own event-loop scheduling on one
# connection, which proves nothing about Postgres row-locking. These tests
# instead follow test_coins_storm.py's pattern: a real engine, a real
# sessionmaker, and one genuinely separate AsyncSession/connection/DB
# transaction per concurrent task, each committing for real - so the outcome
# depends on Postgres's own lock semantics, not asyncio ordering.

_RACE_PHONE = "+919876500001"
_RACE_PURPOSE: OtpPurpose = "login"
_RACE_REAL_CODE = "424242"
_RACE_WRONG_CODE = "000000"


async def _seed_active_otp(maker: async_sessionmaker[AsyncSession]) -> None:
    async with maker() as seed:
        seed.add(
            OtpRequest(
                phone=_RACE_PHONE,
                code_hash=hash_code(_RACE_PHONE, _RACE_PURPOSE, _RACE_REAL_CODE),
                purpose=_RACE_PURPOSE,
                expires_at=datetime.now(UTC) + timedelta(seconds=300),
            )
        )
        await seed.commit()


async def _concurrent_wrong_guess(maker: async_sessionmaker[AsyncSession]) -> None:
    async with maker() as s:
        with contextlib.suppress(OtpVerifyError):
            await verify_otp(
                s, phone=_RACE_PHONE, purpose=_RACE_PURPOSE, code=_RACE_WRONG_CODE, ip=None
            )
        # router.py's own convention (verify_otp_route): commit even on the
        # error path, or the attempt/burn counter never persists - an
        # exception alone would roll the flush back and no attempt would
        # ever accumulate (see router.py:122-126).
        await s.commit()


async def test_concurrent_wrong_guesses_do_not_lose_attempts(database_url: str) -> None:
    """Real-concurrency proof for the fix: fire exactly OTP_MAX_ATTEMPTS (3)
    genuinely concurrent wrong guesses, each its own DB transaction, against
    the SAME active OTP row. Every one of the 3 must be counted - none may be
    lost to a stale read - so the persisted attempts count must land on
    exactly 3, not less. Pre-fix (plain SELECT, no `.with_for_update()`), all
    3 transactions read attempts=0 concurrently and each independently wrote
    back 0+1=1: this assertion fails on that code (final attempts == 1)."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _seed_active_otp(maker)

        await asyncio.gather(*(_concurrent_wrong_guess(maker) for _ in range(OTP_MAX_ATTEMPTS)))

        async with maker() as check:
            row = await check.scalar(
                select(OtpRequest).where(
                    OtpRequest.phone == _RACE_PHONE, OtpRequest.purpose == _RACE_PURPOSE
                )
            )
            assert row is not None
            # The core lost-update assertion: with exactly 3 concurrent wrong
            # guesses and a cap of 3, every guess must be individually
            # counted (no exclusion path is reachable - there is no 4th
            # guess to possibly find the row already burned), so the only
            # way to reach anything other than 3 is a lost update.
            assert row.attempts == OTP_MAX_ATTEMPTS
            assert row.expires_at <= datetime.now(UTC)  # burned at the cap
    finally:
        await engine.dispose()


async def test_concurrent_wrong_guesses_beyond_cap_burn_the_code(database_url: str) -> None:
    """5 genuinely concurrent wrong guesses (more than OTP_MAX_ATTEMPTS=3)
    against one active OTP row: the code must still burn at the real cap
    (attempts reaches at least 3, never fewer - the lost-update bug would
    silently under-count instead), and once burned even the correct code is
    rejected. Guesses that arrive after the burn correctly take the separate
    "no active code" path rather than continuing to increment forever."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    guess_count = 5
    try:
        await _seed_active_otp(maker)

        await asyncio.gather(*(_concurrent_wrong_guess(maker) for _ in range(guess_count)))

        async with maker() as check:
            row = await check.scalar(
                select(OtpRequest).where(
                    OtpRequest.phone == _RACE_PHONE, OtpRequest.purpose == _RACE_PURPOSE
                )
            )
            assert row is not None
            # Never less than the cap (that would be the lost-update bug
            # resurfacing) and never more than the number of real guesses.
            assert OTP_MAX_ATTEMPTS <= row.attempts <= guess_count
            assert row.expires_at <= datetime.now(UTC)  # burned

        # defense-in-depth: burned means even the correct code is dead now
        async with maker() as final_check:
            with pytest.raises(OtpVerifyError):
                await verify_otp(
                    final_check,
                    phone=_RACE_PHONE,
                    purpose=_RACE_PURPOSE,
                    code=_RACE_REAL_CODE,
                    ip=None,
                )
    finally:
        await engine.dispose()
