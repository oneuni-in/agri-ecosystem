"""Mandi price alerts (A-U2 AG-A16).

Subscriptions live here; DELIVERY does not. market_data publishes a
`market.price_alert` event to the `market` stream and notify consumes it
(consumers.EVENT_ROUTES) — the module never imports notify, and the
payload carries no email or phone, so identity stays out of it too. The
event carries `user_id` and notify resolves the rest at send time, which
is the review.approved precedent.

WHY A DIGEST, NOT A THRESHOLD.
"Tell me when tomato crosses ₹30" sounds better than it works: the source
publishes once a day, so a threshold alert is still a once-a-day message,
just one that stays silent on the days the answer is "nothing crossed" —
which is indistinguishable, to the person waiting, from the pull having
failed. A daily digest of what the local mandi actually did is the honest
version of the same promise, and it is what the A-U1 card offers.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from settings import get_settings
from shared.events import publish
from shared.telemetry import get_logger

from .models import PriceAlert
from .service import get_mandi
from .weather import now_ist

logger = get_logger(__name__)

EVENT_STREAM = "market"
EVENT_TYPE = "market.price_alert"


class AlertCapReached(RuntimeError):
    """The user already holds settings.price_alert_max_per_user alerts."""


async def list_alerts(session: AsyncSession, user_id: uuid.UUID) -> list[PriceAlert]:
    rows = await session.scalars(
        select(PriceAlert).where(PriceAlert.user_id == user_id).order_by(PriceAlert.pincode)
    )
    return list(rows)


async def subscribe(session: AsyncSession, user_id: uuid.UUID, pincode: str) -> PriceAlert:
    """Idempotent: subscribing twice returns the existing row.

    That matters because the home card's button has no "already
    subscribed" state — pressing it again must be harmless, not a second
    daily notification or a 409 the UI would have to explain.
    """
    existing = await session.scalar(
        select(PriceAlert).where(PriceAlert.user_id == user_id, PriceAlert.pincode == pincode)
    )
    if existing is not None:
        return existing

    # Cap counted AFTER the idempotent hit, so a user at the cap can still
    # re-press a button for an area they already follow.
    held = len(await list_alerts(session, user_id))
    if held >= get_settings().price_alert_max_per_user:
        raise AlertCapReached
    alert = PriceAlert(user_id=user_id, pincode=pincode)
    session.add(alert)
    await session.flush()
    return alert


async def unsubscribe(session: AsyncSession, user_id: uuid.UUID, alert_id: uuid.UUID) -> bool:
    """Soft-delete one of the CALLER's alerts. False when it is not theirs
    or does not exist — the route turns both into the same 404, so the
    endpoint cannot be used to probe which ids are real (the U2 IDOR
    rule)."""
    alert = await session.scalar(
        select(PriceAlert).where(PriceAlert.id == alert_id, PriceAlert.user_id == user_id)
    )
    if alert is None:
        return False
    alert.deleted_at = now_ist()
    await session.flush()
    return True


async def dispatch_due_alerts(session: AsyncSession, today: date | None = None) -> int:
    """Publish one digest per due alert. Returns how many were published.

    Called by the daily pull AFTER ingest commits, so an alert can only
    describe prices that are actually readable.

    Silent when there is nothing to say: an alert whose district has no
    rows publishes nothing rather than a "no data" notification, which
    would train people to ignore the channel.
    """
    now = today or now_ist().date()
    due = await session.scalars(
        select(PriceAlert).where(
            PriceAlert.last_notified_on.is_(None) | (PriceAlert.last_notified_on < now)
        )
    )

    published = 0
    for alert in due:
        block = await get_mandi(session, alert.pincode)
        if block is None or not block.commodities:
            continue

        # Lead with the biggest absolute mover — the reason to open the
        # notification at all. Ties break on slug so the digest is stable.
        lead = max(block.commodities, key=lambda c: (abs(c.change), c.slug))
        arrow = "▲" if lead.change > 0 else "▼" if lead.change < 0 else "—"
        top = (
            f"{lead.name.en} ₹{lead.price}/{lead.unit}"
            if lead.change == 0
            else f"{lead.name.en} ₹{lead.price}/{lead.unit} {arrow}{abs(lead.change)}"
        )

        await publish(
            EVENT_STREAM,
            EVENT_TYPE,
            {
                "user_id": str(alert.user_id),
                "vars": {
                    "market": block.market,
                    "as_of": block.as_of,
                    "top": top,
                    "count": str(len(block.commodities)),
                },
            },
        )
        alert.last_notified_on = now
        published += 1

    await session.flush()
    logger.info("market.price_alerts_dispatched", extra={"extra_fields": {"published": published}})
    return published
