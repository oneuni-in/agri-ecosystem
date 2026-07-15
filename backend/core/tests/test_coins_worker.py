"""Worker dispatch: identity events award coins idempotently (no Redis needed)."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import service
from modules.coins.worker import handle_event
from shared.events import Event

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _ev(t: str, payload: dict[str, Any]) -> Event:
    return Event(id="1-0", type=t, payload=payload)


async def test_user_registered_awards_signup(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await handle_event(
        db_session,
        _ev(
            "user.registered",
            {
                "user_id": str(uid),
                "agri_id": "AG-1",
                "referral_code": None,
                "phone_prefix": "9198",
            },
        ),
        now=NOW,
    )
    assert await service.balance(db_session, uid) == 100


async def test_user_registered_is_idempotent(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    ev = _ev(
        "user.registered",
        {
            "user_id": str(uid),
            "agri_id": "AG-1",
            "referral_code": None,
            "phone_prefix": "9198",
        },
    )
    await handle_event(db_session, ev, now=NOW)
    await handle_event(db_session, ev, now=NOW)  # redelivery
    assert await service.balance(db_session, uid) == 100


async def test_profile_completed_awards_profile_100(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await handle_event(
        db_session,
        _ev("profile.completed", {"user_id": str(uid), "agri_id": "AG-1", "score": 100}),
        now=NOW,
    )
    assert await service.balance(db_session, uid) == 200


async def test_unknown_event_is_noop(db_session: AsyncSession) -> None:
    await handle_event(db_session, _ev("something.else", {}), now=NOW)  # no raise


async def test_session_resumed_awards_daily_visit(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await handle_event(
        db_session,
        _ev("identity.session_resumed", {"user_id": str(uid)}),
        now=NOW,
    )
    assert await service.balance(db_session, uid) == 5


async def test_session_resumed_is_idempotent_per_day(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    ev = _ev("identity.session_resumed", {"user_id": str(uid)})
    await handle_event(db_session, ev, now=NOW)
    await handle_event(db_session, ev, now=NOW)  # same day, redelivery or a second /me call
    assert await service.balance(db_session, uid) == 5


async def test_session_resumed_awards_again_next_day(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    ev = _ev("identity.session_resumed", {"user_id": str(uid)})
    await handle_event(db_session, ev, now=NOW)
    next_day = NOW.replace(day=NOW.day + 1)
    await handle_event(db_session, ev, now=next_day)
    assert await service.balance(db_session, uid) == 10
