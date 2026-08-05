"""M5 Task 9: ad-order checkout - the billing side of the advertiser
self-serve money path. 🔍 human line review required.

`create_ad_order` is the ONLY place a Razorpay Payment Link is created for
a campaign. It charges EXACTLY the price snapshot ads already computed and
stored on the campaign (`CampaignBillingRef.subtotal_paise`/`gst_paise`/
`price_paise`) - never re-derived, never trusted from the client (threat:
price tampering). Task 10 adds the webhook/reconcile appliers that flip an
order's status from `created` to `paid`/`failed`/`expired`/`refunded` and
write the append-only ledger entry; this module only creates the order and
the outbound Payment Link.

Ordering inside create_ad_order is deliberate: the Razorpay call happens
BEFORE the row is persisted (build the order id, call Razorpay, THEN
savepoint-flush the insert). A RazorpayError therefore leaves nothing in
our DB. The inverse race - the savepoint-flush loses the partial-unique
race (a concurrent checkout already holds the live order) - leaves an
orphaned Razorpay Payment Link that nobody will ever pay; that is an
accepted v1 trade-off (no compensating cancel-payment-link call yet), not
a correctness bug: the loser's response is a clean 409 and the winner's
order is the only one anyone is ever shown a checkout_url for. The link
itself also carries a 24h `expire_by` (money-path review fast-follow), so
even an orphaned/abandoned link eventually reports `payment_link.expired`
rather than staying live forever.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

import uuid6
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.models import AdOrder, BillingLedgerEntry, Invoice
from modules.billing.razorpay_client import RazorpayError
from settings import Settings
from shared import lookups
from shared.lookups import resolve_business, resolve_contact

MAX_DESCRIPTION_LENGTH = 255
LINK_EXPIRY = timedelta(hours=24)

# M5 Task 10: billing's own PendingEvent alias. Defined here (not imported
# from modules.billing.service) because service.py imports THIS module's
# webhook appliers - the reverse import would be a cycle. service.py imports
# this alias back for its own signatures instead of redefining it.
PendingEvent = tuple[str, dict[str, Any]]


async def create_ad_order(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    campaign_id: uuid.UUID,
    buyer_gstin: str | None,
    client: Any,
    settings: Settings,
    now: datetime,
) -> AdOrder:
    """Checkout. Returns the persisted order - `order.razorpay_short_url` is
    the checkout link (also readable later via GET, unlike the old
    response-only tuple). Server-side re-quote is the ONLY price - the
    client never supplies an amount (the route's AdOrderCreateIn has no such
    field, extra="forbid"). `now` is always caller-injected (billing/
    service.py's clock convention), never read here - it only seeds the
    Payment Link's `expire_by`."""
    ref = await lookups.resolve_campaign_billing(session, campaign_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Not Found")
    owner = await lookups.resolve_business(session, ref.business_id)
    if owner is None or owner.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Not Found")  # IDOR: not-yours==404
    if not await lookups.is_servable(session, ref.business_id):
        # fail-closed (M1.5.E precedent, modules/ads/selfserve_router.py's
        # resume route): a suspended/disabled advertiser must not be able to
        # buy a new campaign's way back into inventory just by paying.
        raise HTTPException(status_code=409, detail="business_not_servable")
    if ref.price_paise is None:
        raise HTTPException(status_code=422, detail="not_billable")
    if ref.subtotal_paise is None or ref.gst_paise is None:
        # defensive: a priced campaign (price_paise set) with a missing
        # decomposition is a data-integrity gap on ads' side, not a normal
        # "unpriced/house campaign" case - refuse rather than guess a split.
        raise HTTPException(status_code=422, detail="not_billable")
    if ref.status != "pending_payment":
        raise HTTPException(status_code=409, detail="not_payable")

    # price fields were stored by ads at quote time; billing charges exactly
    # the stored price snapshot - it never re-derives GST. Prefer the full
    # itemized quote ads persisted (Campaign.quote, M5 fast-follow); fall
    # back to the bare 4-number reconstruction only for campaigns quoted
    # before that field existed (ref.quote is None).
    order_id = uuid6.uuid7()
    quote: dict[str, Any] = (
        dict(ref.quote)
        if ref.quote is not None
        else {
            "pricing_model": ref.pricing_model,
            "subtotal_paise": ref.subtotal_paise,
            "gst_paise": ref.gst_paise,
            "total_paise": ref.price_paise,
        }
    )
    quote["campaign_name"] = ref.name
    description = f"Milk.in ads: {ref.name}"[:MAX_DESCRIPTION_LENGTH]
    callback_url = f"{settings.console_base_url}/business/ads?paid={campaign_id}"
    expire_by = int((now + LINK_EXPIRY).timestamp())
    try:
        remote = await client.create_payment_link(
            amount_paise=ref.price_paise,
            description=description,
            reference_id=str(order_id),
            callback_url=callback_url,
            expire_by=expire_by,
            notes={"campaign_id": str(campaign_id), "order_id": str(order_id)},
        )
        plink_id = remote.get("id")
        short_url = remote.get("short_url")
        if not plink_id or not short_url:
            # a 2xx response missing the fields we depend on is as unusable
            # to us as a transport failure - never a KeyError/500.
            raise RazorpayError("payment link response missing id/short_url")
    except RazorpayError as exc:
        raise HTTPException(status_code=503, detail="razorpay_unavailable") from exc

    order = AdOrder(
        id=order_id,
        campaign_id=campaign_id,
        business_id=ref.business_id,
        subtotal_paise=ref.subtotal_paise,
        gst_paise=ref.gst_paise,
        total_paise=ref.price_paise,
        quote=quote,
        buyer_gstin=buyer_gstin,
        razorpay_plink_id=str(plink_id),
        razorpay_short_url=str(short_url),
    )
    try:
        # Savepoint wraps the ADD too (coins/referrals.py get_or_create_code
        # precedent) - not just the flush: session.add() before the savepoint
        # opens would leave `order` a still-pending object in the session
        # after a rolled-back savepoint, and the NEXT autoflush (e.g. the
        # caller's very next SELECT) would silently retry the same doomed
        # INSERT outside any savepoint, corrupting the whole transaction
        # instead of cleanly 409ing.
        async with session.begin_nested():
            session.add(order)
            await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="order_exists") from exc

    return order


# ---------------------------------------------------------------------------
# M5 Task 10: webhook appliers - payment_link.paid / .expired, refund.processed
#
# Called from modules.billing.service.process_webhook_event, itself called
# from router.py's razorpay_webhook AFTER signature verification and
# body-hash dedupe (NN2). Every applier here is therefore already inside a
# verified, deduped, single-delivery transaction - what remains is
# ORDER-LEVEL idempotency (Razorpay retries a delivery with a *different*
# body/event-id - a "rewrapped retry" - which passes the body-hash dedupe as
# a brand-new event) and the price-tamper defense on the amount actually
# paid. Every applier reads defensively (missing/malformed payload -> never
# a KeyError) and locks the AdOrder row FOR UPDATE before deciding.


def invoice_number_for(seq: int, on: date) -> str:
    """Ops-facing sequential invoice number, Indian financial year (starts
    April 1): `MILK-{fy_start_yy}-{fy_end_yy}-{seq:06d}`. Pure function -
    `seq` comes from `nextval('billing.invoice_number_seq')`, `on` is the
    caller's injected clock date, never `date.today()`."""
    fy_start = on.year % 100 if on.month >= 4 else (on.year - 1) % 100
    fy_end = (fy_start + 1) % 100
    return f"MILK-{fy_start:02d}-{fy_end:02d}-{seq:06d}"


async def _pending_ad_notification(
    session: AsyncSession, business_id: uuid.UUID, event_type: str, vars_: dict[str, Any]
) -> PendingEvent | None:
    """Same self-contained-payload shape as billing.service's
    `_pending_notification` (D12 contract): destination/locale resolved
    here, consumed once by the notify consumer. Not imported from
    service.py - that direction would be the import cycle this module must
    avoid (service.py imports ad_orders, not the reverse)."""
    ref = await resolve_business(session, business_id)
    if ref is None or ref.owner_user_id is None:
        return None  # unowned/claimable business - nobody to notify
    contact = await resolve_contact(session, ref.owner_user_id)
    payload: dict[str, Any] = {
        "user_id": str(ref.owner_user_id),
        "locale": (contact.locale if contact else None) or "en",
        "email": contact.email if contact else None,
        "phone": None,
        "vars": {**vars_, "business_name": ref.name},
    }
    return (event_type, payload)


async def apply_payment_link_paid(
    session: AsyncSession, *, payload: dict[str, Any], now: datetime, settings: Settings
) -> tuple[str, list[PendingEvent]]:
    """`payment_link.paid`. Order-level idempotency ON TOP of the webhook
    route's body-hash dedupe: Razorpay's own retries resend the identical
    signed body (caught upstream), but a distinct delivery attempt (new
    `_event_id`/body wrapper for the same plink) is a brand-new event to the
    dedupe layer - so an already-`paid` (or otherwise non-`created`) order
    must be a no-op here, not a second ledger append. THREAT (price
    tamper/partial pay): `payment.amount` is checked against the order's own
    stored `total_paise` - never trusted, never re-derived - and a mismatch
    fails the order closed (no ledger, no activation)."""
    entity = payload.get("payload") or {}
    plink_entity = (entity.get("payment_link") or {}).get("entity") or {}
    payment_entity = (entity.get("payment") or {}).get("entity") or {}
    plink_id = plink_entity.get("id")
    payment_id = payment_entity.get("id")
    amount = payment_entity.get("amount")
    if not plink_id or not payment_id or amount is None:
        return ("unmatched", [])
    try:
        amount_paise = int(amount)
    except (TypeError, ValueError):
        return ("unmatched", [])

    order = await session.scalar(
        select(AdOrder).where(AdOrder.razorpay_plink_id == str(plink_id)).with_for_update()
    )
    if order is None:
        return ("unmatched", [])
    if order.status != "created":
        # status == "paid": order-level idempotency (rewrapped retry/replay
        # of a delivery that already landed). status in ("expired", "failed",
        # "refunded"): a terminal order is never resurrected by a late/racy
        # "paid" webhook - only a live "created" order may be paid. Either
        # way: mark nothing, no ledger, no hook.
        return ("ignored", [])

    if amount_paise != order.total_paise:
        order.status = "failed"
        await session.flush()
        return ("amount_mismatch", [])

    order.status = "paid"
    order.razorpay_payment_id = str(payment_id)
    session.add(
        BillingLedgerEntry(
            entry_type="ad_charge",
            amount_paise=order.total_paise,
            order_id=order.id,
            campaign_id=order.campaign_id,
            business_id=order.business_id,
            razorpay_payment_id=str(payment_id),
            meta={"plink_id": str(plink_id)},
        )
    )
    seq = await session.scalar(text("SELECT nextval('billing.invoice_number_seq')"))
    session.add(
        Invoice(
            order_id=order.id,
            subscription_id=None,
            amount_paise=order.total_paise,
            taxable_paise=order.subtotal_paise,
            gst_paise=order.gst_paise,
            status="paid",
            invoice_number=invoice_number_for(int(seq), now.date()),
            period_start=None,
            period_end=None,
        )
    )
    await session.flush()
    await lookups.notify_campaign_payment(session, order.campaign_id, "paid")

    quote = order.quote or {}
    pending = await _pending_ad_notification(
        session,
        order.business_id,
        "billing.ad_payment_received",
        {"campaign_name": quote.get("campaign_name"), "total_paise": order.total_paise},
    )
    return ("ok", [pending] if pending else [])


async def apply_refund_processed(
    session: AsyncSession, *, payload: dict[str, Any], now: datetime
) -> tuple[str, list[PendingEvent]]:
    """`refund.processed`. Locates the order by the ORIGINAL payment id (a
    refund never carries a plink id); a refund on anything but a `paid`
    order is ignored (already refunded, or never actually paid on our side -
    order-level idempotency, same shape as the paid applier). The ledger
    amount is capped at the order total (a partial/split refund cannot drive
    the append-only ledger negative past what was ever charged) and floored
    at a strictly-negative append - `amount_paise=0` would trip the ledger's
    own sign CHECK constraint, so a zero/negative refund amount is treated
    as unmatched rather than crashing the webhook transaction."""
    entity = payload.get("payload") or {}
    refund_entity = (entity.get("refund") or {}).get("entity") or {}
    payment_id = refund_entity.get("payment_id")
    amount = refund_entity.get("amount")
    if not payment_id or amount is None:
        return ("unmatched", [])
    try:
        amount_paise = int(amount)
    except (TypeError, ValueError):
        return ("unmatched", [])

    order = await session.scalar(
        select(AdOrder).where(AdOrder.razorpay_payment_id == str(payment_id)).with_for_update()
    )
    if order is None:
        return ("unmatched", [])
    if order.status != "paid":
        return ("ignored", [])

    capped = min(amount_paise, order.total_paise)
    if capped <= 0:
        return ("unmatched", [])

    session.add(
        BillingLedgerEntry(
            entry_type="ad_refund",
            amount_paise=-capped,
            order_id=order.id,
            campaign_id=order.campaign_id,
            business_id=order.business_id,
            razorpay_payment_id=str(payment_id),
            meta={"refund_id": str(refund_entity.get("id") or "")},
        )
    )
    order.status = "refunded"
    await session.flush()
    # CARRY-FORWARD (Task 7 ledger contract): the hook zero-outs
    # budget_serves_total and pauses the campaign. No re-pay path from
    # paused/refunded is built here - that is a fresh checkout on a fresh
    # order (the partial-unique index on ad_orders excludes 'refunded').
    await lookups.notify_campaign_payment(session, order.campaign_id, "refunded")
    return ("ok", [])


async def apply_payment_link_expired(
    session: AsyncSession, *, payload: dict[str, Any], now: datetime
) -> tuple[str, list[PendingEvent]]:
    """`payment_link.expired`. Only a live `created` order expires; a `paid`
    order ignores a late expiry notification (Razorpay raced the payment
    against its own expiry) and no other status is reachable here anyway.
    No campaign hook - the campaign stays `pending_payment`, and the
    partial-unique index on `ad_orders` (live = created|paid) excludes
    `expired`, so the advertiser can start a fresh checkout immediately."""
    entity = payload.get("payload") or {}
    plink_entity = (entity.get("payment_link") or {}).get("entity") or {}
    plink_id = plink_entity.get("id")
    if not plink_id:
        return ("unmatched", [])
    order = await session.scalar(
        select(AdOrder).where(AdOrder.razorpay_plink_id == str(plink_id)).with_for_update()
    )
    if order is None:
        return ("unmatched", [])
    if order.status != "created":
        return ("ignored", [])
    order.status = "expired"
    await session.flush()
    return ("ok", [])
