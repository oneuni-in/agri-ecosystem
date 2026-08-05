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


async def creative_moderation_counts(
    session: AsyncSession, campaign_id: uuid.UUID
) -> tuple[int, int]:
    """(approved_count, pending_count) for a campaign's creatives. Public -
    modules/ads/admin_router.py's status guard (decision 14) reuses this to
    apply the same moderation half of the activation gate to staff-driven
    transitions, not just maybe_activate's own."""
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
    if campaign.price_paise is None:
        raise LifecycleError("not_priced")
    creative_count = await session.scalar(
        select(func.count()).select_from(Creative).where(Creative.campaign_id == campaign.id)
    )
    if not creative_count:
        raise LifecycleError("no_creatives")
    campaign.status = "pending_payment"
    await session.flush()


async def maybe_activate(session: AsyncSession, campaign: Campaign) -> bool:
    """-> active iff paid_at is set AND >=1 approved creative AND 0 pending
    creatives. Only ever transitions INTO active from pending_moderation
    (payment->moderation path) or paused (advertiser resume path); every
    other status is left untouched. Returns whether it activated.

    THREAT (race): a concurrent webhook-paid + last-creative-approve can
    each read the other's precondition as unmet and both commit, stranding
    a paid+fully-approved campaign in pending_moderation forever. Closed by
    taking a row lock on the campaign here, under BOTH callers (the
    moderation approve path previously never touched the campaign row at
    all when the gate failed, so nothing serialized it against a
    concurrent payment) - the conjunction is now always evaluated against a
    locked, freshly-read row. sweep_lifecycle's recovery pass is the
    backstop for any campaign that still ends up stranded (e.g. from code
    predating this lock)."""
    locked = await session.scalar(
        select(Campaign).where(Campaign.id == campaign.id).with_for_update()
    )
    if locked is None or locked.status not in _ACTIVATABLE_FROM:
        return False
    approved, pending = await creative_moderation_counts(session, locked.id)
    if locked.paid_at is not None and approved >= 1 and pending == 0:
        locked.status = "active"
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
        # Only ever try to activate off the payment->moderation path. paused
        # is in _ACTIVATABLE_FROM for the RESUME route (an explicit advertiser
        # action), not for a payment webhook - otherwise a late/duplicate
        # "paid" event could resurrect an advertiser- or enforcement-paused
        # campaign behind the owner's back.
        if campaign.status == "pending_moderation":
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
    display_status's own precedence), not "exhausted".

    Also runs a recovery pass over any campaign stranded in
    pending_moderation with paid_at already set - the backstop for
    maybe_activate's row-locked conjunction check (see its docstring): a
    campaign that somehow still slipped through - e.g. a bug or a manual
    DB fixup - gets a chance to activate on the next tick instead of
    sitting unservable forever with no advertiser-visible recovery path."""
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
    stranded = (
        await session.scalars(
            select(Campaign).where(
                Campaign.status == "pending_moderation",
                Campaign.paid_at.is_not(None),
            )
        )
    ).all()
    recovered = sum([await maybe_activate(session, campaign) for campaign in stranded])
    await session.flush()
    return (expired.rowcount or 0) + (exhausted.rowcount or 0) + recovered
