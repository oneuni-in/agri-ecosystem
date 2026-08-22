"""A-U2 AG-A16 — mandi price-alert subscriptions and their daily digest.

The properties worth defending here are about a user's own data and about
not becoming noise:

  - a subscription is idempotent, capped, and deletable;
  - one user can never see or delete another's, and cannot even learn
    that another's exists;
  - a digest goes out ONCE a day even though the pull is re-run;
  - nothing is published when there is nothing to say.

Delivery is notify's job. What is asserted here is that the right event
reaches the bus with the right payload — market_data must not import
notify, so the event IS the contract.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any, cast

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.market_data.alerts import (
    EVENT_STREAM,
    EVENT_TYPE,
    AlertCapReached,
    dispatch_due_alerts,
    list_alerts,
    subscribe,
    unsubscribe,
)
from modules.market_data.ingest import ingest_records
from modules.market_data.models import PriceAlert
from modules.notify.consumers import EVENT_ROUTES, STREAMS
from settings import get_settings
from shared.cache import get_redis

from .d26_helpers import api  # noqa: F401 — the shared client fixture
from .test_market_mandi import _records, _row

pytestmark = pytest.mark.anyio

USER = uuid.UUID("01a00000-0000-7000-8000-00000000a001")
OTHER = uuid.UUID("01a00000-0000-7000-8000-00000000b002")


async def _seed_prices(session: AsyncSession) -> None:
    await ingest_records(
        session,
        _records(
            [
                _row(
                    district="Coimbatore",
                    market="Coimbatore market",
                    arrival_date="14/08/2026",
                    min_price=2300,
                    max_price=2350,
                    modal_price=2300,
                ),
                _row(
                    district="Coimbatore",
                    market="Coimbatore market",
                    arrival_date="15/08/2026",
                    min_price=2380,
                    max_price=2410,
                    modal_price=2400,
                ),
            ]
        ),
    )
    await session.flush()


# ── subscriptions ────────────────────────────────────────────────────


async def test_subscribing_twice_is_idempotent(db_session: AsyncSession) -> None:
    """The home card's button has no 'already subscribed' state, so a
    second press must be harmless — not a duplicate row, and not a second
    notification a day."""
    first = await subscribe(db_session, USER, "641001")
    second = await subscribe(db_session, USER, "641001")
    assert first.id == second.id
    rows = (await db_session.scalars(select(PriceAlert).where(PriceAlert.user_id == USER))).all()
    assert len(rows) == 1


async def test_the_per_user_cap_holds(db_session: AsyncSession) -> None:
    cap = get_settings().price_alert_max_per_user
    for n in range(cap):
        await subscribe(db_session, USER, f"64100{n}")
    with pytest.raises(AlertCapReached):
        await subscribe(db_session, USER, "600001")

    # At the cap, re-pressing an area they ALREADY follow still works —
    # the cap must not turn an idempotent button into an error.
    again = await subscribe(db_session, USER, "641000")
    assert again.pincode == "641000"


async def test_unsubscribe_only_touches_your_own(db_session: AsyncSession) -> None:
    mine = await subscribe(db_session, USER, "641001")
    theirs = await subscribe(db_session, OTHER, "641002")

    # Another user's id behaves EXACTLY like a nonexistent one, so the
    # endpoint cannot be used to discover which ids are real.
    assert await unsubscribe(db_session, USER, theirs.id) is False
    assert await unsubscribe(db_session, USER, uuid.uuid4()) is False

    assert await unsubscribe(db_session, USER, mine.id) is True
    # Soft delete: an unsubscribe is auditable, not a silent gap.
    assert mine.deleted_at is not None


async def test_resubscribing_after_unsubscribe_works(db_session: AsyncSession) -> None:
    """Turning an alert off must not be a one-way door.

    The soft delete leaves the row in place, but `uq_price_alerts_user_pincode`
    is a plain unique on (user_id, pincode) that does NOT exclude deleted
    rows — and subscribe()'s idempotency probe cannot see soft-deleted rows,
    because SoftDeleteMixin hides them from ORM selects. So the second
    subscribe used to fall through to an INSERT and die on the constraint.

    Found in AG-U5, when /account grew a "Turn off" button: before that there
    was no way to unsubscribe from any UI, so the path was unreachable. The
    user-visible symptom was a 500 from the home's mandi card, forever, for
    any pincode the farmer had ever turned off.
    """
    first = await subscribe(db_session, USER, "641001")
    assert await unsubscribe(db_session, USER, first.id) is True

    again = await subscribe(db_session, USER, "641001")

    # The SAME row comes back, revived rather than duplicated — the unique
    # constraint leaves no other correct answer.
    assert again.id == first.id
    assert again.deleted_at is None
    # And it is visible again, which is the whole point of re-subscribing.
    assert [a.id for a in await list_alerts(db_session, USER)] == [first.id]


async def test_reviving_an_alert_still_respects_the_cap(db_session: AsyncSession) -> None:
    """Reviving IS subscribing, so it cannot be a side door around the cap."""
    cap = get_settings().price_alert_max_per_user
    old = await subscribe(db_session, USER, "600001")
    await unsubscribe(db_session, USER, old.id)

    # Fill every slot with other areas while that one sits soft-deleted.
    for n in range(cap):
        await subscribe(db_session, USER, f"64100{n}")

    with pytest.raises(AlertCapReached):
        await subscribe(db_session, USER, "600001")
    # Still off, and still not counted.
    assert len(await list_alerts(db_session, USER)) == cap


async def test_a_revived_alert_can_be_notified_the_same_day(
    db_session: AsyncSession, tn_geo_sample: None, otp_redis: object
) -> None:
    """The once-a-day latch belongs to the old subscription, not the new one.

    Without clearing `last_notified_on`, a farmer who received today's digest,
    unsubscribed, then changed their mind would get silence until tomorrow —
    the new subscription would start life already marked as sent.
    """
    await _seed_prices(db_session)
    first = await subscribe(db_session, USER, "641001")
    assert await dispatch_due_alerts(db_session, today=date(2026, 8, 16)) == 1
    assert first.last_notified_on == date(2026, 8, 16)

    await unsubscribe(db_session, USER, first.id)
    again = await subscribe(db_session, USER, "641001")
    assert again.last_notified_on is None

    assert await dispatch_due_alerts(db_session, today=date(2026, 8, 16)) == 1


# ── the daily digest ─────────────────────────────────────────────────


async def _drain(stream: str) -> list[dict[str, Any]]:
    """Every event on the bus stream, decoded.

    The cast mirrors shared/events.py: redis-py types stream replies as a
    loose bytes|str union, but the shared client sets decode_responses,
    so these really are str.
    """
    entries = cast(list[tuple[str, dict[str, str]]], await get_redis().xrange(stream) or [])
    return [cast(dict[str, Any], json.loads(fields["payload"])) for _id, fields in entries]


async def test_a_due_alert_publishes_one_digest(
    db_session: AsyncSession, tn_geo_sample: None, otp_redis: object
) -> None:
    await _seed_prices(db_session)
    await subscribe(db_session, USER, "641001")

    published = await dispatch_due_alerts(db_session, today=date(2026, 8, 16))
    assert published == 1

    events = await _drain(EVENT_STREAM)
    assert len(events) == 1
    payload = events[0]
    assert payload["user_id"] == str(USER)
    variables: dict[str, str] = payload["vars"]
    assert variables["market"] == "Coimbatore market"
    assert variables["as_of"] == "2026-08-15"
    # Leads with the mover, in the same per-kg unit as the card.
    assert variables["top"] == "Paddy (common) ₹24.0/kg ▲1.0"
    assert variables["count"] == "1"
    # No destination in the payload: notify resolves the recipient, which
    # is what keeps market_data independent of identity.
    assert "email" not in payload and "phone" not in payload


async def test_the_digest_goes_out_once_a_day(
    db_session: AsyncSession, tn_geo_sample: None, otp_redis: object
) -> None:
    """The pull is deliberately re-runnable — the source serves only the
    live day — so re-running it must not notify twice."""
    await _seed_prices(db_session)
    await subscribe(db_session, USER, "641001")

    assert await dispatch_due_alerts(db_session, today=date(2026, 8, 16)) == 1
    assert await dispatch_due_alerts(db_session, today=date(2026, 8, 16)) == 0
    assert len(await _drain(EVENT_STREAM)) == 1

    # Tomorrow it is due again.
    assert await dispatch_due_alerts(db_session, today=date(2026, 8, 17)) == 1


async def test_nothing_is_published_when_there_is_nothing_to_say(
    db_session: AsyncSession, tn_geo_sample: None, otp_redis: object
) -> None:
    """An area with no ingested rows sends NO notification. A "no data
    today" message would train people to ignore the channel."""
    await subscribe(db_session, USER, "641001")  # no prices ingested
    assert await dispatch_due_alerts(db_session, today=date(2026, 8, 16)) == 0
    assert await _drain(EVENT_STREAM) == []

    alert = (await db_session.scalars(select(PriceAlert))).one()
    # Not latched either, so the alert is still due once data arrives.
    assert alert.last_notified_on is None


# ── wiring ───────────────────────────────────────────────────────────


def test_notify_consumes_the_market_stream() -> None:
    """market_data publishes; notify routes. If either half is missing the
    subscription silently never delivers, which is the failure this
    catches."""
    assert EVENT_STREAM in STREAMS
    assert EVENT_ROUTES[EVENT_TYPE][0] == "mandi_price_alert"


# ── endpoints ────────────────────────────────────────────────────────


async def test_alert_routes_require_auth(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    """Private by default on SecureRouter: these read and write a user's
    own data and are deliberately absent from public_routes.txt."""
    client, _session = api
    assert (await client.get("/market/alerts")).status_code == 401
    assert (await client.post("/market/alerts", json={"pincode": "641001"})).status_code == 401
    assert (await client.delete(f"/market/alerts/{uuid.uuid4()}")).status_code == 401
