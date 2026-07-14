"""D12: modules emit events; the notify consumer maps them to dispatches."""

import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.consumers import EVENT_ROUTES, handle_event
from modules.notify.models import Notification
from shared.events import Event


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
    } == EVENT_ROUTES
