"""D12: modules emit events; the notify consumer maps them to dispatches."""

import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.consumers import EVENT_ROUTES, handle_event
from modules.notify.drivers import MockPushDriver
from modules.notify.models import Notification, PushSubscription
from shared.events import Event
from shared.flags import FeatureFlag


def _event(event_type: str, **vars_: str) -> tuple[Event, str]:
    user_id = str(uuid.uuid4())
    return (
        Event(
            id="1-1",
            type=event_type,
            payload={
                "user_id": user_id,
                "agri_id": "@asha",
                "locale": "ta",
                "email": None,
                "phone": None,
                "vars": dict(vars_),
            },
        ),
        user_id,
    )


async def test_signup_event_creates_welcome_notification(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    event, user_id = _event("identity.signup_completed", agri_id="@asha")
    await handle_event(db_session, event)
    row = (await db_session.scalars(select(Notification))).one()
    assert row.template_key == "welcome"
    assert str(row.user_id) == user_id
    assert row.locale == "ta"


async def test_unknown_event_type_is_ignored(db_session: AsyncSession, otp_redis: Redis) -> None:
    event, _ = _event("identity.something_else")
    await handle_event(db_session, event)
    assert (await db_session.scalars(select(Notification))).all() == []


def test_route_table_matches_seeded_templates() -> None:
    assert {
        "identity.signup_completed": ("welcome", frozenset({"email"})),
        "identity.login_new_device": ("login_new_device", frozenset({"sms", "email"})),
        "identity.role_changed": ("role_changed", frozenset()),
        "notify.announce": ("generic_announce", frozenset({"email"})),
        "business.claimed": ("claim_approved", frozenset()),
        "directory.claim_rejected": ("claim_rejected", frozenset()),
        "directory.verification_approved": ("verification_approved", frozenset()),
        "directory.verification_rejected": ("verification_rejected", frozenset()),
        "review.approved": ("review_approved", frozenset()),
        # D28: leads also push - subscriptions resolve by user_id inside
        # notify, so no destination is needed in the event payload.
        "lead.created": ("lead_received", frozenset({"push"})),
        "lead.responded": ("lead_response", frozenset({"push"})),
        # D20 billing/dunning routes (backend/core/modules/notify/consumers.py)
        "billing.payment_failed": ("dunning_payment_failed", frozenset({"email"})),
        "billing.dunning_reminder": ("dunning_reminder", frozenset({"email"})),
        "billing.subscription_canceled": ("subscription_canceled", frozenset({"email"})),
        "billing.subscription_activated": ("subscription_activated", frozenset({"email"})),
    } == EVENT_ROUTES


async def test_business_claimed_creates_in_app_notification(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    user_id = uuid.uuid4()
    event = Event(
        id="1-0",
        type="business.claimed",
        payload={
            "user_id": str(user_id),
            "business_id": str(uuid.uuid4()),
            "vars": {"business_name": "Anbu Seeds"},
        },
    )
    await handle_event(db_session, event)
    notification = await db_session.scalar(
        select(Notification).where(Notification.user_id == user_id)
    )
    assert notification is not None
    # Notification.body doesn't exist - body renders at read time from
    # payload (modules/notify/models.py); assert the var flows through.
    assert notification.payload.get("business_name") == "Anbu Seeds"


async def test_review_approved_creates_in_app_notification(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    user_id = uuid.uuid4()
    event = Event(
        id="1-0",
        type="review.approved",
        payload={
            "user_id": str(user_id),
            "review_id": str(uuid.uuid4()),
            "target_type": "business",
            "target_id": str(uuid.uuid4()),
            "vars": {},
        },
    )
    await handle_event(db_session, event)
    notification = await db_session.scalar(
        select(Notification).where(Notification.user_id == user_id)
    )
    assert notification is not None
    assert notification.template_key == "review_approved"


async def test_lead_created_creates_in_app_notification(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    user_id = uuid.uuid4()
    event = Event(
        id="1-0",
        type="lead.created",
        payload={
            "user_id": str(user_id),
            "inquiry_id": str(uuid.uuid4()),
            "business_id": str(uuid.uuid4()),
            "vars": {"business_name": "Anbu Seeds", "inquiry_type": "contact"},
        },
    )
    await handle_event(db_session, event)
    notification = await db_session.scalar(
        select(Notification).where(Notification.user_id == user_id)
    )
    assert notification is not None
    assert notification.template_key == "lead_received"
    assert notification.payload.get("business_name") == "Anbu Seeds"
    assert notification.payload.get("inquiry_type") == "contact"


async def test_lead_created_pushes_to_subscribed_device(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    """D28: the lead.created route fans out to push when the user has a
    subscription and the flag is on (preference/flag/no-sub cases are
    pinned in test_notify_push.py - this covers the consumer wiring)."""
    user_id = uuid.uuid4()
    flag = await db_session.get(FeatureFlag, "notify.push_enabled")
    assert flag is not None
    flag.enabled = True
    db_session.add(
        PushSubscription(
            user_id=user_id,
            endpoint="https://fcm.googleapis.com/fcm/send/consumer",
            p256dh="p",
            auth="a",
        )
    )
    await db_session.flush()
    event = Event(
        id="1-0",
        type="lead.created",
        payload={
            "user_id": str(user_id),
            "inquiry_id": str(uuid.uuid4()),
            "business_id": str(uuid.uuid4()),
            "vars": {"business_name": "Anbu Seeds", "inquiry_type": "contact"},
        },
    )
    await handle_event(db_session, event)
    assert len(MockPushDriver.outbox) == 1
    endpoint, title, _body = MockPushDriver.outbox[0]
    assert endpoint == "https://fcm.googleapis.com/fcm/send/consumer"
    assert title == "New enquiry — Anbu Seeds"


async def test_lead_responded_creates_in_app_notification(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    user_id = uuid.uuid4()
    event = Event(
        id="1-0",
        type="lead.responded",
        payload={
            "user_id": str(user_id),
            "inquiry_id": str(uuid.uuid4()),
            "vars": {"business_name": "Anbu Seeds"},
        },
    )
    await handle_event(db_session, event)
    notification = await db_session.scalar(
        select(Notification).where(Notification.user_id == user_id)
    )
    assert notification is not None
    assert notification.template_key == "lead_response"
    assert notification.payload.get("business_name") == "Anbu Seeds"


async def test_claim_rejected_notification_carries_reason(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    user_id = uuid.uuid4()
    event = Event(
        id="1-0",
        type="directory.claim_rejected",
        payload={
            "user_id": str(user_id),
            "business_id": str(uuid.uuid4()),
            "vars": {"business_name": "Fake Farm", "reason": "stock photo"},
        },
    )
    await handle_event(db_session, event)
    notification = await db_session.scalar(
        select(Notification).where(Notification.user_id == user_id)
    )
    assert notification is not None
    assert notification.payload.get("reason") == "stock photo"
