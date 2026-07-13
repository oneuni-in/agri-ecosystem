"""D12 engine: preference routing, rate cap, retry w/ backoff, dead-letter."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.drivers import MockEmailDriver, MockNotifySmsDriver
from modules.notify.models import Delivery, Notification, Preference
from modules.notify.service import (
    MAX_DELIVERY_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    NotifyRequest,
    dispatch,
    retry_due_deliveries,
)
from shared.flags import FeatureFlag

NOW = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)


def _request(**overrides: object) -> NotifyRequest:
    defaults: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "template_key": "login_new_device",
        "payload": {"device": "Chrome on Android"},
        "locale": "en",
        "email": "farmer@example.com",
        "phone": "+919876500001",
        "channels": frozenset({"sms", "email"}),
    }
    defaults.update(overrides)
    return NotifyRequest(**defaults)  # type: ignore[arg-type]


async def _enable_email_flag(session: AsyncSession) -> None:
    flag = await session.get(FeatureFlag, "notify.email_enabled")
    assert flag is not None
    flag.enabled = True
    await session.flush()


async def test_in_app_row_always_created(db_session: AsyncSession, otp_redis: Redis) -> None:
    request = _request(channels=frozenset())
    notification = await dispatch(db_session, request, now=NOW)
    assert notification is not None and notification.read_at is None
    deliveries = (await db_session.scalars(select(Delivery))).all()
    assert deliveries == []  # no extra channels requested


async def test_sms_opt_out_routes_in_app_only(db_session: AsyncSession, otp_redis: Redis) -> None:
    await _enable_email_flag(db_session)
    request = _request()
    db_session.add(Preference(user_id=request.user_id, channel="sms", enabled=False))
    await db_session.flush()
    await dispatch(db_session, request, now=NOW)
    channels = {d.channel for d in (await db_session.scalars(select(Delivery))).all()}
    assert channels == {"email"}  # sms suppressed by preference
    assert MockNotifySmsDriver.outbox == []
    assert len(MockEmailDriver.outbox) == 1


async def test_email_skipped_when_flag_off(db_session: AsyncSession, otp_redis: Redis) -> None:
    await dispatch(db_session, _request(channels=frozenset({"email"})), now=NOW)
    assert MockEmailDriver.outbox == []
    assert (await db_session.scalars(select(Delivery))).all() == []


async def test_missing_destination_skips_channel(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    await _enable_email_flag(db_session)
    await dispatch(db_session, _request(email=None), now=NOW)
    channels = {d.channel for d in (await db_session.scalars(select(Delivery))).all()}
    assert channels == {"sms"}


async def test_rate_cap_drops_whole_notification(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    request = _request(channels=frozenset())
    from settings import get_settings

    cap = get_settings().notify_user_hourly_cap
    for _ in range(cap):
        assert await dispatch(db_session, request, now=NOW) is not None
    assert await dispatch(db_session, request, now=NOW) is None
    count = len((await db_session.scalars(select(Notification))).all())
    assert count == cap


async def test_failed_send_schedules_backoff_then_dead_letters(
    db_session: AsyncSession, otp_redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _enable_email_flag(db_session)

    async def boom(self: object, to: str, subject: str, body: str) -> str | None:
        raise RuntimeError("provider down")

    monkeypatch.setattr(MockEmailDriver, "send", boom)
    await dispatch(db_session, _request(channels=frozenset({"email"})), now=NOW)
    delivery = (await db_session.scalars(select(Delivery))).one()
    assert delivery.status == "failed"
    assert delivery.attempts == 1
    assert delivery.next_attempt_at == NOW + timedelta(seconds=RETRY_BACKOFF_SECONDS[0])

    # drive retries until dead
    for attempt in range(2, MAX_DELIVERY_ATTEMPTS + 1):
        due_at = delivery.next_attempt_at
        retried = await retry_due_deliveries(db_session, now=due_at)
        assert retried == 1
        await db_session.refresh(delivery)
        assert delivery.attempts == attempt
    assert delivery.status == "dead"
    assert delivery.next_attempt_at is None


async def test_retry_succeeds_and_marks_sent(
    db_session: AsyncSession, otp_redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _enable_email_flag(db_session)
    calls = {"n": 0}
    real_send = MockEmailDriver.send

    async def flaky(self: MockEmailDriver, to: str, subject: str, body: str) -> str | None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("blip")
        return await real_send(self, to, subject, body)

    monkeypatch.setattr(MockEmailDriver, "send", flaky)
    await dispatch(db_session, _request(channels=frozenset({"email"})), now=NOW)
    delivery = (await db_session.scalars(select(Delivery))).one()
    assert delivery.status == "failed"
    await retry_due_deliveries(db_session, now=delivery.next_attempt_at)
    await db_session.refresh(delivery)
    assert delivery.status == "sent"
    assert len(MockEmailDriver.outbox) == 1
