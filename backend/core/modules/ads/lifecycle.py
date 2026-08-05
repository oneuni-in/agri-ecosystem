"""Campaign lifecycle engine (M5 Task 7): the ONE place status transitions
happen. Non-negotiable: a campaign activates iff BOTH payment (paid_at set)
AND moderation (>=1 approved creative, 0 pending creatives) have cleared -
see `maybe_activate`. Nothing else in the codebase may flip a campaign into
`active`.

No commits in here - callers own the transaction (repo choreography, D16/D21
precedent): every function below flushes only. `on_payment_event` in
particular runs INSIDE billing's webhook transaction via the registered
CampaignPaymentHook (shared/lookups.py); a commit here would split that tx.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign, Creative
from shared.telemetry import get_logger

logger = get_logger(__name__)

PAYABLE_FROM = frozenset({"draft"})
# refund pauses from any state where money is (or was) on the line; draft/
# archived campaigns were never paid so they are not in this set.
_REFUNDABLE_FROM = frozenset({"active", "paused", "pending_payment", "pending_moderation"})
# maybe_activate only ever promotes a campaign INTO active from these two
# states - pending_moderation is the normal payment->moderation path, paused
# is the advertiser resume path. It never touches draft/pending_payment/
# archived/exhausted/expired.
_ACTIVATABLE_FROM = frozenset({"pending_moderation", "paused"})


class LifecycleError(Exception):
    """.code is the API's 409 detail - not-found stays a 404 via the
    router's own ownership guard, it never reaches this class."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def _creative_counts(session: AsyncSession, campaign_id: uuid.UUID) -> tuple[int, int]:
    """(approved_count, pending_count) for a campaign's creatives."""
    rows = (
        await session.execute(
            select(Creative.moderation_status, func.count())
            .where(Creative.campaign_id == campaign_id)
            .group_by(Creative.moderation_status)
        )
    ).all()
    counts = {status: n for status, n in rows}
    return int(counts.get("approved", 0)), int(counts.get("pending", 0))


async def request_checkout(session: AsyncSession, campaign: Campaign) -> None:
    """draft -> pending_payment. Requires a priced campaign with at least one
    creative uploaded - Task 9's billing checkout route calls this before it
    ever talks to Razorpay."""
    if campaign.status not in PAYABLE_FROM:
        raise LifecycleError("not_payable")
    creative_count = await session.scalar(
        select(func.count()).select_from(Creative).where(Creative.campaign_id == campaign.id)
    )
    if campaign.price_paise is None or not creative_count:
        raise LifecycleError("no_creatives")
    campaign.status = "pending_payment"
    await session.flush()


async def maybe_activate(session: AsyncSession, campaign: Campaign) -> bool:
    """-> active iff paid_at is set AND >=1 approved creative AND 0 pending
    creatives. Only ever transitions INTO active from pending_moderation
    (payment->moderation path) or paused (advertiser resume path); every
    other status is left untouched. Returns whether it activated."""
    if campaign.status not in _ACTIVATABLE_FROM:
        return False
    approved, pending = await _creative_counts(session, campaign.id)
    if campaign.paid_at is not None and approved >= 1 and pending == 0:
        campaign.status = "active"
        await session.flush()
        return True
    return False


async def on_payment_event(session: AsyncSession, campaign_id: uuid.UUID, event: str) -> None:
    """The registered CampaignPaymentHook (shared/lookups.py, Task 5's seam).
    Runs inside billing's webhook transaction - flush only, never commit."""
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        # money is recorded in billing regardless; reconcile surfaces the gap.
        logger.warning(
            "ads.payment_hook_unmatched",
            extra={"extra_fields": {"campaign_id": str(campaign_id), "event": event}},
        )
        return

    if event == "paid":
        campaign.paid_at = datetime.now(UTC)
        if campaign.status == "pending_payment":
            campaign.status = "pending_moderation"
        await session.flush()
        await maybe_activate(session, campaign)
        return

    if event == "refunded":
        if campaign.status in _REFUNDABLE_FROM:
            campaign.status = "paused"
            # Close the resume-after-refund hole: paid_at is deliberately NOT
            # cleared (it must stay true history), so a naive resume would
            # pass maybe_activate's paid_at check. Instead we zero the
            # remaining budget (total := used) so the campaign is durably
            # non-serving even if resumed - consume_budget's conditional
            # UPDATE (modules/ads/service.py) never fires once used>=total,
            # and display_status reports "exhausted" for it.
            campaign.budget_serves_total = campaign.budget_serves_used
            await session.flush()
            logger.warning(
                "ads.campaign_refund_paused",
                extra={"extra_fields": {"campaign_id": str(campaign_id)}},
            )
        return

    logger.warning(
        "ads.payment_hook_unknown_event",
        extra={"extra_fields": {"campaign_id": str(campaign_id), "event": event}},
    )


async def demote_to_moderation(session: AsyncSession, campaign: Campaign) -> None:
    """active -> pending_moderation (Task 8: editing a creative on a live
    campaign re-enters moderation before it can serve again)."""
    if campaign.status == "active":
        campaign.status = "pending_moderation"
        await session.flush()


def display_status(campaign: Campaign, *, today: date) -> str:
    """The raw `status` column plus the two derived states that only ever
    show up read-side until the next worker sweep durably flips them
    (sweep_lifecycle)."""
    if campaign.status == "active":
        if campaign.flight_end < today:
            return "expired"
        if (
            campaign.budget_serves_total is not None
            and campaign.budget_serves_used >= campaign.budget_serves_total
        ):
            return "exhausted"
    return campaign.status


async def sweep_lifecycle(session: AsyncSession, *, today: date) -> int:
    """Durable UPDATE of the two derived states (worker tick, 6h cadence).
    Order matters: the expiry sweep runs first so a campaign that is BOTH
    past its flight and budget-exhausted lands on "expired" (matching
    display_status's own precedence), not "exhausted"."""
    expired = cast(
        CursorResult[Any],
        await session.execute(
            update(Campaign)
            .where(Campaign.status == "active", Campaign.flight_end < today)
            .values(status="expired")
        ),
    )
    exhausted = cast(
        CursorResult[Any],
        await session.execute(
            update(Campaign)
            .where(
                Campaign.status == "active",
                Campaign.budget_serves_total.is_not(None),
                Campaign.budget_serves_used >= Campaign.budget_serves_total,
            )
            .values(status="exhausted")
        ),
    )
    await session.flush()
    return (expired.rowcount or 0) + (exhausted.rowcount or 0)
