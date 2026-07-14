"""OTP throttle boundaries (D07.C): the suite proves the numbers, not the
intent - every limit constant is pinned by an explicit boundary test here.
Cooldown/escalation elapse is simulated by deleting the Redis keys (their TTLs
are asserted instead of slept through)."""

import logging

import pytest
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from modules.identity.otp_limits import (
    OTP_ISSUES_PER_DEVICE_PER_DAY,
    OTP_ISSUES_PER_IP_PER_DAY,
    OTP_ISSUES_PER_PHONE_PER_DAY,
    OTP_VERIFIES_PER_IP_PER_DAY,
    RESEND_COOLDOWNS_SECONDS,
    SUSPICIOUS_PHONES_PER_IP,
)
from modules.identity.otp_throttle import (
    OtpRateLimited,
    assert_issue_allowed,
    assert_verify_allowed,
    register_issue,
)
from settings import get_settings
from shared.audit import AuditEntry
from shared.db import reset_engine

PHONE = "+919876543210"
IP = "203.0.113.7"


def phone_n(n: int) -> str:
    return f"+9198765{n:05d}"


async def clear_cooldown(redis: Redis, phone: str = PHONE) -> None:
    """Simulate the cooldown elapsing without sleeping."""
    await redis.delete(f"otp:cd:{phone}")


async def issue_once(redis: Redis, phone: str = PHONE, ip: str | None = IP) -> None:
    await clear_cooldown(redis, phone)
    await assert_issue_allowed(phone, ip, None)
    await register_issue(phone, ip)


async def assert_cooldown_is(redis: Redis, expected: int, phone: str = PHONE) -> None:
    """Pin the armed cooldown to the constant (1s tolerance for clock ticks)."""
    ttl = int(await redis.ttl(f"otp:cd:{phone}"))
    assert expected - 1 <= ttl <= expected


# --- resend cooldown escalation: 30 -> 60 -> 300, capped, resettable ---------


async def test_cooldown_escalates_30_60_300_and_caps(otp_redis: Redis) -> None:
    expected = [30, 60, 300, 300]  # 4th issue stays at the ladder maximum
    assert list(RESEND_COOLDOWNS_SECONDS) == expected[:3]
    for cooldown in expected:
        await issue_once(otp_redis)
        await assert_cooldown_is(otp_redis, cooldown)


async def test_request_during_cooldown_blocked_with_retry_after(otp_redis: Redis) -> None:
    await issue_once(otp_redis)
    with pytest.raises(OtpRateLimited) as excinfo:
        await assert_issue_allowed(PHONE, IP, None)
    assert 0 < excinfo.value.retry_after <= RESEND_COOLDOWNS_SECONDS[0]


async def test_escalation_resets_after_quiet_window(otp_redis: Redis) -> None:
    await issue_once(otp_redis)
    await issue_once(otp_redis)
    await assert_cooldown_is(otp_redis, RESEND_COOLDOWNS_SECONDS[1])
    # simulate RESEND_ESCALATION_RESET_SECONDS of quiet: the level key expires
    await otp_redis.delete(f"otp:cdlvl:{PHONE}")
    await issue_once(otp_redis)
    await assert_cooldown_is(otp_redis, RESEND_COOLDOWNS_SECONDS[0])


async def test_cooldown_is_per_phone(otp_redis: Redis) -> None:
    await issue_once(otp_redis, phone_n(1))
    # a different phone from the same IP is not in cooldown
    await assert_issue_allowed(phone_n(2), IP, None)


# --- daily caps: phone 5, IP 20, device 20 ------------------------------------


async def test_phone_daily_cap_allows_5_blocks_6th(otp_redis: Redis) -> None:
    for _ in range(OTP_ISSUES_PER_PHONE_PER_DAY):
        await issue_once(otp_redis)  # 5 issues succeed
    await clear_cooldown(otp_redis)
    with pytest.raises(OtpRateLimited) as excinfo:
        await assert_issue_allowed(PHONE, IP, None)
    assert excinfo.value.retry_after > 0  # window TTL, not a cooldown


async def test_phone_daily_cap_trip_emits_burst_audit(
    otp_redis: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    for _ in range(OTP_ISSUES_PER_PHONE_PER_DAY):
        await issue_once(otp_redis)
    await clear_cooldown(otp_redis)
    with caplog.at_level(logging.WARNING), pytest.raises(OtpRateLimited):
        await assert_issue_allowed(PHONE, IP, None)
    assert "otp_abuse.burst_issues" in caplog.text
    assert PHONE not in caplog.text  # audit hook never logs the phone


async def test_phone_daily_cap_trip_writes_committed_audit_row(
    otp_redis: Redis,
    database_url: str,
    admin_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """otp.abuse_burst_issues lands as a real row (D12), not just a log line.
    _audit_system opens its OWN committed session via get_sessionmaker(),
    which reads settings.database_url - point it at the migrated test DB
    (mirrors the otp_redis fixture's REDIS_URL override) so the committed row
    is visible here, then clean it up via admin credentials (app_rt has no
    DELETE on schema audit)."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    reset_engine()
    try:
        for _ in range(OTP_ISSUES_PER_PHONE_PER_DAY):
            await issue_once(otp_redis)
        await clear_cooldown(otp_redis)
        with pytest.raises(OtpRateLimited):
            await assert_issue_allowed(PHONE, IP, None)

        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                rows = (
                    await session.scalars(
                        select(AuditEntry).where(AuditEntry.action == "otp.abuse_burst_issues")
                    )
                ).all()
                assert len(rows) == 1
                assert PHONE not in str(rows[0].meta)
        finally:
            await engine.dispose()
    finally:
        admin_engine = create_async_engine(admin_database_url, poolclass=NullPool)
        async with admin_engine.connect() as conn:
            await conn.execute(text("DELETE FROM audit.entries WHERE action LIKE 'otp.abuse%'"))
            await conn.commit()
        await admin_engine.dispose()


async def test_ip_daily_cap_allows_20_blocks_21st(otp_redis: Redis) -> None:
    for n in range(OTP_ISSUES_PER_IP_PER_DAY):
        await issue_once(otp_redis, phone_n(n))  # 20 distinct phones, one IP
    with pytest.raises(OtpRateLimited):
        await assert_issue_allowed(phone_n(99), IP, None)


async def test_device_daily_cap_allows_20_blocks_21st(otp_redis: Redis) -> None:
    device = "device-fp-1"
    for n in range(OTP_ISSUES_PER_DEVICE_PER_DAY):
        # ip=None isolates the device dimension from the identical IP cap
        await clear_cooldown(otp_redis, phone_n(n))
        await assert_issue_allowed(phone_n(n), None, device)
        await register_issue(phone_n(n), None)
    with pytest.raises(OtpRateLimited):
        await assert_issue_allowed(phone_n(99), None, device)


# --- verify budget: 50 per IP per day -----------------------------------------


async def test_verify_ip_cap_allows_50_blocks_51st(otp_redis: Redis) -> None:
    for _ in range(OTP_VERIFIES_PER_IP_PER_DAY):
        await assert_verify_allowed(IP)
    with pytest.raises(OtpRateLimited):
        await assert_verify_allowed(IP)


async def test_verify_cap_is_per_ip(otp_redis: Redis) -> None:
    for _ in range(OTP_VERIFIES_PER_IP_PER_DAY):
        await assert_verify_allowed(IP)
    await assert_verify_allowed("198.51.100.9")  # other IPs unaffected


# --- abuse telemetry: many phones per IP --------------------------------------


async def test_many_phones_per_ip_emits_audit(
    otp_redis: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        for n in range(SUSPICIOUS_PHONES_PER_IP - 1):
            await issue_once(otp_redis, phone_n(n))
        assert "otp_abuse.many_phones_per_ip" not in caplog.text  # below threshold
        await issue_once(otp_redis, phone_n(SUSPICIOUS_PHONES_PER_IP - 1))
    assert "otp_abuse.many_phones_per_ip" in caplog.text
