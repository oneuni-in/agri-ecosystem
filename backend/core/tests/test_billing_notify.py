"""billing.* events -> notify templates (D18 lesson: routes and seeded
templates land together, so a dispatched event renders, not warns)."""

import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import User
from modules.notify.consumers import EVENT_ROUTES, STREAMS, handle_event
from modules.notify.models import Notification
from shared.events import Event


def test_billing_stream_and_routes_registered() -> None:
    assert "billing" in STREAMS
    assert EVENT_ROUTES["billing.payment_failed"] == (
        "dunning_payment_failed",
        frozenset({"email"}),
    )
    assert EVENT_ROUTES["billing.dunning_reminder"] == ("dunning_reminder", frozenset({"email"}))
    assert EVENT_ROUTES["billing.subscription_canceled"] == (
        "subscription_canceled",
        frozenset({"email"}),
    )
    assert EVENT_ROUTES["billing.subscription_activated"] == (
        "subscription_activated",
        frozenset({"email"}),
    )
    assert "billing.subscription_renewed" not in EVENT_ROUTES  # renewals are silent by design


async def test_payment_failed_event_creates_notification(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    user = User(phone="+916374344002", agri_id=f"AG-{uuid.uuid4().hex[:8]}")
    db_session.add(user)
    await db_session.flush()
    event = Event(
        id="1-1",
        type="billing.payment_failed",
        payload={
            "user_id": str(user.id),
            "locale": "ta",
            "email": "owner@example.com",
            "phone": None,
            "vars": {"business_name": "Kovai Mills", "tier": "growth"},
        },
    )
    await handle_event(db_session, event)
    notification = await db_session.scalar(
        select(Notification).where(Notification.user_id == user.id)
    )
    assert notification is not None
    assert notification.template_key == "dunning_payment_failed"
