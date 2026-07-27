"""Notify engine (D12): the ONLY send path.

Every send flows dispatch() -> preferences -> flag -> driver. Modules never
touch drivers (import-linter contract); they publish events and the consumer
calls dispatch(). In-app is unconditional (and not toggleable); sms/email are
opt-out via notify.preferences rows. The per-user hourly cap is the
harassment brake: over-cap events drop entirely, with a metric.

Retries: a failed delivery gets exponential backoff via next_attempt_at and
dies (status 'dead') after MAX_DELIVERY_ATTEMPTS - the delivery-level
dead-letter, distinct from the bus-level :dlq stream."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.drivers import (
    ExpiredSubscriptionError,
    get_email_driver,
    get_notify_sms_driver,
    get_push_driver,
)
from modules.notify.models import Delivery, Notification, Preference, PushSubscription
from modules.notify.rendering import load_template, render_template
from settings import get_settings
from shared.cache import get_redis
from shared.flags import flag_enabled
from shared.metrics import NOTIFY_DROPPED, NOTIFY_SENT
from shared.telemetry import get_logger

logger = get_logger(__name__)

MAX_DELIVERY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (60, 300, 1500)


@dataclass(frozen=True, slots=True)
class NotifyRequest:
    user_id: uuid.UUID
    template_key: str
    payload: dict[str, Any]
    locale: str = "en"
    email: str | None = None
    phone: str | None = None
    channels: frozenset[str] = field(default_factory=frozenset)  # beyond in_app


async def channel_enabled(session: AsyncSession, user_id: uuid.UUID, channel: str) -> bool:
    """No row means enabled: preferences store opt-outs."""
    row = await session.scalar(
        select(Preference.enabled).where(
            Preference.user_id == user_id, Preference.channel == channel
        )
    )
    return True if row is None else bool(row)


async def _within_rate_cap(user_id: uuid.UUID, now: datetime) -> bool:
    cap = get_settings().notify_user_hourly_cap
    key = f"notify:cap:{user_id}:{now.strftime('%Y%m%d%H')}"
    redis = get_redis()
    count = int(await redis.incr(key))
    if count == 1:
        await redis.expire(key, 3600)
    return count <= cap


async def dispatch(
    session: AsyncSession, request: NotifyRequest, *, now: datetime | None = None
) -> Notification | None:
    """Create the in-app notification (always) + channel deliveries (filtered
    by preference/flag/destination), attempting each send once inline."""
    now = now or datetime.now(UTC)
    if not await _within_rate_cap(request.user_id, now):
        NOTIFY_DROPPED.labels("rate_cap").inc()
        logger.warning(
            "notify.dropped.rate_cap",
            extra={"extra_fields": {"template_key": request.template_key}},
        )
        return None
    notification = Notification(
        user_id=request.user_id,
        template_key=request.template_key,
        payload=request.payload,
        locale=request.locale,
    )
    session.add(notification)
    await session.flush()
    NOTIFY_SENT.labels("in_app", "sent").inc()

    for channel in sorted(request.channels & {"sms", "email", "push"}):
        if not await channel_enabled(session, request.user_id, channel):
            NOTIFY_DROPPED.labels("preference").inc()
            continue
        flag_name = {"email": "notify.email_enabled", "push": "notify.push_enabled"}.get(channel)
        if flag_name is not None and not await flag_enabled(flag_name, session=session):
            NOTIFY_DROPPED.labels("flag").inc()
            continue
        if channel == "push":
            # Push needs no destination in the request: subscriptions resolve
            # by user_id here, one delivery per subscribed device (D28).
            subs = (
                await session.scalars(
                    select(PushSubscription).where(PushSubscription.user_id == request.user_id)
                )
            ).all()
            if not subs:
                NOTIFY_DROPPED.labels("no_destination").inc()
                continue
            for sub in subs:
                delivery = Delivery(
                    notification_id=notification.id, channel="push", destination=sub.endpoint
                )
                session.add(delivery)
                await session.flush()
                await _attempt(session, delivery, notification, now=now)
            continue
        destination = request.email if channel == "email" else request.phone
        if not destination:
            NOTIFY_DROPPED.labels("no_destination").inc()
            continue
        delivery = Delivery(
            notification_id=notification.id, channel=channel, destination=destination
        )
        session.add(delivery)
        await session.flush()
        await _attempt(session, delivery, notification, now=now)
    return notification


async def _attempt(
    session: AsyncSession, delivery: Delivery, notification: Notification, *, now: datetime
) -> None:
    template = await load_template(
        session,
        key=notification.template_key,
        channel=delivery.channel,
        locale=notification.locale,
    )
    delivery.attempts += 1
    if template is None:
        # a template gap is permanent - retrying cannot fix it
        delivery.status = "dead"
        delivery.next_attempt_at = None
        delivery.last_error = "template_missing"
        NOTIFY_SENT.labels(delivery.channel, "dead").inc()
        return
    if delivery.channel == "push":
        # Keys are re-fetched by endpoint so the retry path still works after
        # a restart; a pruned subscription is permanent (gone means gone).
        subscription = await session.scalar(
            select(PushSubscription).where(PushSubscription.endpoint == delivery.destination)
        )
        if subscription is None:
            delivery.status = "dead"
            delivery.next_attempt_at = None
            delivery.last_error = "subscription_gone"
            NOTIFY_SENT.labels("push", "dead").inc()
            await session.flush()
            return
    else:
        subscription = None
    try:
        if delivery.channel == "push":
            assert subscription is not None
            title = render_template(template.subject or "", notification.payload)
            body = render_template(template.body, notification.payload)
            try:
                delivery.provider_ref = await get_push_driver().send(
                    {
                        "endpoint": subscription.endpoint,
                        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                    },
                    title,
                    body,
                )
            except ExpiredSubscriptionError:
                await session.delete(subscription)
                delivery.status = "dead"
                delivery.next_attempt_at = None
                delivery.last_error = "ExpiredSubscriptionError"
                NOTIFY_SENT.labels("push", "dead").inc()
                await session.flush()
                return
        elif delivery.channel == "email":
            body = render_template(template.body, notification.payload, escape_html=True)
            subject = render_template(template.subject or "", notification.payload)
            assert delivery.destination is not None
            delivery.provider_ref = await get_email_driver().send(
                delivery.destination, subject, body
            )
        else:
            body = render_template(template.body, notification.payload)
            assert delivery.destination is not None
            delivery.provider_ref = await get_notify_sms_driver().send(delivery.destination, body)
        delivery.status = "sent"
        delivery.next_attempt_at = None
        delivery.last_error = None
        NOTIFY_SENT.labels(delivery.channel, "sent").inc()
    except Exception as exc:
        delivery.last_error = type(exc).__name__  # class only - message may carry PII
        if delivery.attempts >= MAX_DELIVERY_ATTEMPTS:
            delivery.status = "dead"
            delivery.next_attempt_at = None
            NOTIFY_SENT.labels(delivery.channel, "dead").inc()
        else:
            delivery.status = "failed"
            delivery.next_attempt_at = now + timedelta(
                seconds=RETRY_BACKOFF_SECONDS[delivery.attempts - 1]
            )
            NOTIFY_SENT.labels(delivery.channel, "failed").inc()
    await session.flush()


async def retry_due_deliveries(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Re-attempt every failed delivery whose backoff has elapsed."""
    now = now or datetime.now(UTC)
    due = (
        await session.scalars(
            select(Delivery).where(Delivery.status == "failed", Delivery.next_attempt_at <= now)
        )
    ).all()
    for delivery in due:
        notification = await session.get(Notification, delivery.notification_id)
        assert notification is not None  # FK guarantees existence
        await _attempt(session, delivery, notification, now=now)
    return len(due)
