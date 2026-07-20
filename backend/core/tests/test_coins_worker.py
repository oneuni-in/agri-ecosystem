"""Worker dispatch: identity events award coins idempotently (no Redis needed)."""

import uuid
from datetime import UTC, datetime, timedelta
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


async def test_business_claimed_awards_once_per_business(db_session: AsyncSession) -> None:
    """D16 non-negotiable 1: same business can never credit twice - not on
    event redelivery, and not even for a different claimant user."""
    uid = uuid.uuid4()
    business_id = str(uuid.uuid4())
    event = _ev("business.claimed", {"user_id": str(uid), "business_id": business_id})
    await handle_event(db_session, event, now=NOW)
    assert await service.balance(db_session, uid) == 200
    # redelivery: no double credit
    await handle_event(db_session, event, now=NOW)
    assert await service.balance(db_session, uid) == 200
    # different user, same business (can't happen via API - no unclaim path -
    # but the idem key must hold anyway): no credit
    other = uuid.uuid4()
    await handle_event(
        db_session,
        _ev("business.claimed", {"user_id": str(other), "business_id": business_id}),
        now=NOW,
    )
    assert await service.balance(db_session, other) == 0
    assert await service.balance(db_session, uid) == 200


async def test_business_claimed_different_businesses_both_award(
    db_session: AsyncSession,
) -> None:
    uid = uuid.uuid4()
    for business_id in (str(uuid.uuid4()), str(uuid.uuid4())):
        await handle_event(
            db_session,
            _ev("business.claimed", {"user_id": str(uid), "business_id": business_id}),
            now=NOW,
        )
    assert await service.balance(db_session, uid) == 400


async def test_review_approved_awards_coins(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    rid = uuid.uuid4()
    await handle_event(
        db_session,
        _ev(
            "review.approved",
            {
                "user_id": str(uid),
                "review_id": str(rid),
                "target_type": "business",
                "target_id": str(uuid.uuid4()),
                "vars": {},
            },
        ),
        now=NOW,
    )
    assert await service.balance(db_session, uid) == 20


async def test_review_approved_replay_is_idempotent(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    rid = uuid.uuid4()
    event = _ev(
        "review.approved",
        {
            "user_id": str(uid),
            "review_id": str(rid),
            "target_type": "business",
            "target_id": str(uuid.uuid4()),
            "vars": {},
        },
    )
    await handle_event(db_session, event, now=NOW)
    await handle_event(db_session, event, now=NOW)  # redelivery, same review_id
    assert await service.balance(db_session, uid) == 20


async def test_review_approved_weekly_cap_five(db_session: AsyncSession) -> None:
    """D18 non-negotiable 2: at most 5 review_approved awards per user per
    rolling week - the 6th distinct review within 7 days must not award, and
    must not raise (CapExceededError is a normal outcome, swallowed by the
    worker)."""
    uid = uuid.uuid4()
    for _ in range(5):
        await handle_event(
            db_session,
            _ev(
                "review.approved",
                {
                    "user_id": str(uid),
                    "review_id": str(uuid.uuid4()),
                    "target_type": "business",
                    "target_id": str(uuid.uuid4()),
                    "vars": {},
                },
            ),
            now=NOW,
        )
    assert await service.balance(db_session, uid) == 100
    await handle_event(
        db_session,
        _ev(
            "review.approved",
            {
                "user_id": str(uid),
                "review_id": str(uuid.uuid4()),
                "target_type": "business",
                "target_id": str(uuid.uuid4()),
                "vars": {},
            },
        ),
        now=NOW,
    )
    assert await service.balance(db_session, uid) == 100  # capped, no exception escapes


async def test_review_approved_award_resumes_next_week(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    for _ in range(5):
        await handle_event(
            db_session,
            _ev(
                "review.approved",
                {
                    "user_id": str(uid),
                    "review_id": str(uuid.uuid4()),
                    "target_type": "business",
                    "target_id": str(uuid.uuid4()),
                    "vars": {},
                },
            ),
            now=NOW,
        )
    assert await service.balance(db_session, uid) == 100
    later = NOW + timedelta(days=8)
    await handle_event(
        db_session,
        _ev(
            "review.approved",
            {
                "user_id": str(uid),
                "review_id": str(uuid.uuid4()),
                "target_type": "business",
                "target_id": str(uuid.uuid4()),
                "vars": {},
            },
        ),
        now=later,
    )
    assert await service.balance(db_session, uid) == 120
