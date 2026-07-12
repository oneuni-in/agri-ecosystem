"""Redis throttles for OTP issue/verify (D07.C).

Every number comes from otp_limits.py; this module only enforces. Counters are
fixed windows (INCR + EXPIRE on first hit, like shared/security.RateLimiter)
but there is deliberately NO in-memory fallback here: if Redis is down, OTP
issuance fails closed. An unthrottled credential endpoint during an outage is
a worse failure than a 500 (SMS flooding = vendor bill, brute-force = account
takeover).

Check order in assert_issue_allowed: cooldown first (a retry during cooldown
must not burn daily quota), then phone/IP/device daily caps. The daily INCRs
count denied-by-later-check attempts too; that only ever under-serves an
already-abusive source, never extends a window.
"""

from redis.asyncio import Redis

from modules.identity.otp_limits import (
    DAY_SECONDS,
    OTP_ISSUES_PER_DEVICE_PER_DAY,
    OTP_ISSUES_PER_IP_PER_DAY,
    OTP_ISSUES_PER_PHONE_PER_DAY,
    OTP_VERIFIES_PER_IP_PER_DAY,
    RESEND_COOLDOWNS_SECONDS,
    RESEND_ESCALATION_RESET_SECONDS,
    SUSPICIOUS_PHONES_PER_IP,
)
from shared.audit import audit
from shared.cache import get_redis
from shared.db import get_sessionmaker
from shared.telemetry import get_logger

logger = get_logger(__name__)


class OtpRateLimited(Exception):
    """A throttle tripped; retry_after is seconds until the window frees up."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"otp rate limited, retry after {retry_after}s")
        self.retry_after = max(1, retry_after)


async def _audit_system(action: str, metadata: dict[str, object]) -> None:
    """System-actor audit row in its own committed session: abuse records must
    survive the request's 429 rollback. Best-effort - an audit outage must not
    take OTP issuance down with it."""
    try:
        async with get_sessionmaker()() as session:
            await audit(session, action=action, metadata=metadata)
            await session.commit()
    except Exception as exc:
        logger.warning(
            "audit.write_failed",
            extra={"extra_fields": {"action": action, "exc_type": type(exc).__name__}},
        )


def _cooldown_key(phone: str) -> str:
    return f"otp:cd:{phone}"


def _escalation_key(phone: str) -> str:
    return f"otp:cdlvl:{phone}"


async def _bump_daily(redis: Redis, key: str, cap: int) -> None:
    """Increment a fixed 24h window counter; raise once the cap is exceeded."""
    count = int(await redis.incr(key))
    if count == 1:
        await redis.expire(key, DAY_SECONDS)
    if count > cap:
        raise OtpRateLimited(int(await redis.ttl(key)))


async def assert_issue_allowed(phone: str, ip: str | None, device_fingerprint: str | None) -> None:
    """Raise OtpRateLimited if any issue throttle blocks this request."""
    redis = get_redis()
    cooldown_ttl = int(await redis.ttl(_cooldown_key(phone)))
    if cooldown_ttl > 0:
        raise OtpRateLimited(cooldown_ttl)
    try:
        await _bump_daily(redis, f"otp:day:phone:{phone}", OTP_ISSUES_PER_PHONE_PER_DAY)
    except OtpRateLimited:
        # burst-issue audit hook (D07.F): phone stays out of the log line
        logger.warning(
            "otp_abuse.burst_issues",
            extra={"extra_fields": {"ip": ip, "cap": OTP_ISSUES_PER_PHONE_PER_DAY}},
        )
        await _audit_system(
            "otp.abuse_burst_issues", {"ip": ip, "cap": OTP_ISSUES_PER_PHONE_PER_DAY}
        )
        raise
    if ip is not None:
        await _bump_daily(redis, f"otp:day:ip:{ip}", OTP_ISSUES_PER_IP_PER_DAY)
    if device_fingerprint is not None:
        await _bump_daily(redis, f"otp:day:dev:{device_fingerprint}", OTP_ISSUES_PER_DEVICE_PER_DAY)


async def register_issue(phone: str, ip: str | None) -> None:
    """Record a successful issue: escalate the resend cooldown, track phones/IP.

    Escalation: the Nth issue inside the reset window arms a cooldown of
    RESEND_COOLDOWNS_SECONDS[min(N-1, last)]; a quiet
    RESEND_ESCALATION_RESET_SECONDS resets the ladder to the start.
    """
    redis = get_redis()
    level = int(await redis.incr(_escalation_key(phone)))
    await redis.expire(_escalation_key(phone), RESEND_ESCALATION_RESET_SECONDS)
    step = min(level, len(RESEND_COOLDOWNS_SECONDS)) - 1
    await redis.set(_cooldown_key(phone), "1", ex=RESEND_COOLDOWNS_SECONDS[step])
    if ip is not None:
        phones_key = f"otp:phones:{ip}"
        added = int(await redis.sadd(phones_key, phone))
        await redis.expire(phones_key, DAY_SECONDS)
        distinct = int(await redis.scard(phones_key))
        if added and distinct >= SUSPICIOUS_PHONES_PER_IP:
            # many-phones-per-IP audit hook (D07.F)
            logger.warning(
                "otp_abuse.many_phones_per_ip",
                extra={"extra_fields": {"ip": ip, "distinct_phones": distinct}},
            )
            await _audit_system(
                "otp.abuse_many_phones_per_ip", {"ip": ip, "distinct_phones": distinct}
            )


async def assert_verify_allowed(ip: str | None) -> None:
    """Raise OtpRateLimited once an IP exceeds its daily verify budget."""
    if ip is None:
        return
    await _bump_daily(get_redis(), f"otp:vday:ip:{ip}", OTP_VERIFIES_PER_IP_PER_DAY)
