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
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.invoice_pdf import render_invoice_pdf
from modules.billing.models import AdOrder, BillingLedgerEntry, Invoice
from modules.billing.razorpay_client import RazorpayError
from settings import Settings, get_settings
from shared import lookups, storage
from shared.telemetry import get_logger

logger = get_logger(__name__)

MAX_DESCRIPTION_LENGTH = 255
LINK_EXPIRY = timedelta(hours=24)
# M5 Task 12: bounded work queue per worker tick, same shape as every other
# sweep in this codebase (dunning/lifecycle precedent) - a backlog drains
# over several ticks rather than one tick doing unbounded work.
INVOICE_PDF_SWEEP_LIMIT = 20

# M5 Task 10: billing's own PendingEvent alias. Defined here (not imported
# from modules.billing.service) because service.py imports THIS module's
# webhook appliers - the reverse import would be a cycle. service.py imports
# this alias back for its own signatures instead of redefining it.
PendingEvent = tuple[str, dict[str, Any]]


async def campaign_charged_paise(session: AsyncSession, campaign_id: uuid.UUID) -> int | None:
    """M5 Task 13 fast-follow: the registered CampaignChargedResolver
    (shared/lookups.py) - ads' campaign stats route reads net retained
    money through this, never `ads.campaigns` columns. `ledger_entries.
    amount_paise` is signed by construction (ck_billing_ledger_entries_sign:
    ad_charge > 0, ad_refund < 0), so a plain SUM across every row for the
    campaign already IS the net - no separate charge/refund bookkeeping
    needed. None when the campaign has no ledger rows at all (never
    charged - house/unpaid campaign), which Postgres' SUM over zero rows
    already returns as NULL; that is distinct from a real net of exactly 0
    (charged, then fully refunded) - callers must not collapse the two."""
    total = await session.scalar(
        select(func.sum(BillingLedgerEntry.amount_paise)).where(
            BillingLedgerEntry.campaign_id == campaign_id
        )
    )
    return int(total) if total is not None else None


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
# a KeyError/AttributeError) and locks the AdOrder row FOR UPDATE before
# deciding.


def invoice_number_for(seq: int, on: date) -> str:
    """Ops-facing sequential invoice number, Indian financial year (starts
    April 1): `MILK-{fy_start_yy}-{fy_end_yy}-{seq:06d}`. Pure function -
    `seq` comes from `nextval('billing.invoice_number_seq')`, `on` is the
    caller's injected clock date, never `date.today()`."""
    fy_start = on.year % 100 if on.month >= 4 else (on.year - 1) % 100
    fy_end = (fy_start + 1) % 100
    return f"MILK-{fy_start:02d}-{fy_end:02d}-{seq:06d}"


def _nested_entity(container: Any, *keys: str) -> dict[str, Any]:
    """Defensive nested-dict descent for Razorpay webhook payloads: any
    level that isn't a dict (missing key, `None`, a list, a bare string -
    Razorpay's own retries have been known to reshape malformed bodies)
    resolves to `{}` instead of raising `AttributeError`/`TypeError`.
    Callers then just see missing fields and answer `("unmatched", [])`,
    same as a plain missing key."""
    current: Any = container
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _terminal_paid_warning(plink_id: str, order_id: str, status: str) -> None:
    """A signature-verified `payment_link.paid` event means Razorpay
    genuinely captured money - it must never be silently swallowed just
    because our local order row is in a dead-end state (failed/refunded, or
    a partial-unique collision on an expired->paid flip). Ops/reconcile has
    to chase the real disposition by hand; this is the loud paper trail.

    Takes `order_id` as a plain str, not the ORM object: after a savepoint
    rollback (the IntegrityError-collision caller below) the object's
    attributes are expired, and AsyncSession has no implicit lazy-load - a
    bare `order.id` access there raises `MissingGreenlet`, not a fresh
    SELECT. Callers capture the id BEFORE attempting the mutation."""
    logger.warning(
        "billing.ad_paid_on_terminal_order",
        extra={
            "extra_fields": {
                "plink_id": plink_id,
                "order_id": order_id,
                "order_status": status,
            }
        },
    )


async def apply_payment_link_paid(
    session: AsyncSession, *, payload: dict[str, Any], now: datetime, settings: Settings
) -> tuple[str, list[PendingEvent]]:
    """`payment_link.paid`. Order-level idempotency ON TOP of the webhook
    route's body-hash dedupe: Razorpay's own retries resend the identical
    signed body (caught upstream), but a distinct delivery attempt (new
    `_event_id`/body wrapper for the same plink) is a brand-new event to the
    dedupe layer - so an already-`paid` order must be a no-op here, not a
    second ledger append.

    `expired` orders ALSO proceed (not just `created`): Razorpay's own
    expiry webhook can race a genuine payment, and a signature-verified paid
    event must never be dropped just because we already gave up on the
    link. The partial-unique index (`created`|`paid` live per campaign) is
    the collision backstop for the case where a re-checkout already created
    a second live order for the same campaign while this one sat expired -
    caught as an `IntegrityError` from the flush inside a savepoint, never
    left half-applied.

    THREAT (price tamper/partial pay): `payment.amount` is checked against
    the order's own stored `total_paise` - never trusted, never re-derived -
    and a mismatch fails the order closed (no ledger, no activation)."""
    plink_entity = _nested_entity(payload, "payload", "payment_link", "entity")
    payment_entity = _nested_entity(payload, "payload", "payment", "entity")
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
    order_id_str = str(order.id)  # captured now - see _terminal_paid_warning's docstring
    if order.status == "paid":
        # rewrapped retry/replay of a delivery that already landed - order-
        # level idempotency, not an anomaly worth a warning.
        return ("ignored", [])
    if order.status not in ("created", "expired"):
        # failed/refunded: see _terminal_paid_warning - money was captured
        # for a dead-end order; log loudly rather than dropping it.
        _terminal_paid_warning(str(plink_id), order_id_str, order.status)
        return ("ignored_terminal", [])

    if amount_paise != order.total_paise:
        # THREAT (price tamper/partial pay). NOTE: this strict `!=` depends
        # on the Payment Link's `accept_partial` defaulting False
        # (create_ad_order never sets it) - never enable partial payments
        # on payment links without revisiting this check.
        order.status = "failed"
        order.razorpay_payment_id = str(payment_id)  # forensics + refund matching later
        await session.flush()
        return ("amount_mismatch", [])

    try:
        async with session.begin_nested():
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
    except IntegrityError:
        # expired->paid collided with the partial-unique index: a
        # re-checkout already made a second live (created/paid) order for
        # this campaign while this one sat expired. The savepoint rolled
        # back cleanly - the outer webhook transaction is still healthy.
        # `order`'s attributes are now expired (post-rollback) - use the
        # id captured before the savepoint, never `order.id` here.
        _terminal_paid_warning(str(plink_id), order_id_str, "expired")
        return ("ignored_terminal", [])

    await lookups.notify_campaign_payment(session, order.campaign_id, "paid")
    # Task 12 sends the invoice email as the payment confirmation; no
    # in-app/email notify event is emitted from here (ruled: an unrouted
    # event is dead weight until that wiring lands).
    return ("ok", [])


async def apply_refund_processed(
    session: AsyncSession, *, payload: dict[str, Any], now: datetime
) -> tuple[str, list[PendingEvent]]:
    """`refund.processed`. Locates the order by the ORIGINAL payment id (a
    refund never carries a plink id). Balance-based accounting - Razorpay
    supports split/partial refunds, so a single order can receive several
    `refund.processed` events: `already_refunded` is read back from the
    ledger itself (sum of prior `ad_refund` rows for this order, which are
    stored negative), and this delivery is capped at whatever headroom
    remains (`total_paise - already_refunded`). A delivery that has no
    headroom left (a duplicate/retried delivery of a refund already fully
    applied) computes a non-positive amount and is ignored - no row, no
    double-count. The campaign is only paused/budget-zeroed once the
    running total reaches the order's `total_paise` - a partial goodwill
    refund must not kill a still-serving campaign.

    REFUND-LEVEL IDEMPOTENCY (on top of the balance cap above): a rewrapped
    retry of the SAME real-world refund (fresh Razorpay event id, a
    differently-serialized body) passes the webhook route's body-hash
    dedupe as a brand-new event, same as the paid-webhook rewrap case - and
    the balance computation alone does NOT catch it, because two identical
    partial-refund deliveries each look like legitimate remaining headroom
    from the ledger's point of view. `refund_id` (Razorpay's own refund
    entity id) is therefore mandatory - a missing/malformed one is
    `("unmatched", [])`, since idempotency depends on it - and checked
    against the ledger (`meta->>'refund_id'`) INSIDE the order's `FOR
    UPDATE` window before the balance is even computed. The ledger append
    itself runs inside a savepoint so the DB-level backstop
    (`uq_billing_ledger_entries_refund_once`) can never surface as an
    unhandled 500 if two deliveries for the same refund id race past the
    app-level check."""
    refund_entity = _nested_entity(payload, "payload", "refund", "entity")
    payment_id = refund_entity.get("payment_id")
    refund_id = refund_entity.get("id")
    amount = refund_entity.get("amount")
    if not payment_id or not refund_id or amount is None:
        return ("unmatched", [])
    try:
        amount_paise = int(amount)
    except (TypeError, ValueError):
        return ("unmatched", [])
    refund_id_str = str(refund_id)

    order = await session.scalar(
        select(AdOrder).where(AdOrder.razorpay_payment_id == str(payment_id)).with_for_update()
    )
    if order is None:
        return ("unmatched", [])
    order_id_str = str(order.id)  # captured now - see apply_payment_link_paid's precedent
    if order.status not in ("paid", "refunded"):
        return ("ignored", [])

    duplicate = await session.scalar(
        select(BillingLedgerEntry.id).where(
            BillingLedgerEntry.order_id == order.id,
            BillingLedgerEntry.entry_type == "ad_refund",
            BillingLedgerEntry.meta["refund_id"].astext == refund_id_str,
        )
    )
    if duplicate is not None:
        return ("ignored", [])

    already_refunded_raw = await session.scalar(
        select(func.coalesce(func.sum(BillingLedgerEntry.amount_paise), 0)).where(
            BillingLedgerEntry.order_id == order.id,
            BillingLedgerEntry.entry_type == "ad_refund",
        )
    )
    already_refunded = -int(already_refunded_raw or 0)  # ledger rows are stored negative
    headroom = order.total_paise - already_refunded
    refund_amount = min(amount_paise, headroom)
    if refund_amount <= 0:
        # nothing left to refund - a retried/duplicate delivery of an
        # already-fully-applied refund, or a malformed non-positive amount.
        return ("ignored", [])

    fully_refunded = already_refunded + refund_amount >= order.total_paise
    try:
        async with session.begin_nested():
            session.add(
                BillingLedgerEntry(
                    entry_type="ad_refund",
                    amount_paise=-refund_amount,
                    order_id=order.id,
                    campaign_id=order.campaign_id,
                    business_id=order.business_id,
                    razorpay_payment_id=str(payment_id),
                    meta={"refund_id": refund_id_str},
                )
            )
            if fully_refunded:
                order.status = "refunded"
            await session.flush()
    except IntegrityError:
        # DB backstop (uq_billing_ledger_entries_refund_once): a concurrent
        # delivery for the SAME refund id won the race between the
        # app-level duplicate check above and this flush. The savepoint
        # rolled back cleanly - never a 500, never a double-counted refund.
        logger.warning(
            "billing.ad_refund_duplicate_id",
            extra={"extra_fields": {"order_id": order_id_str, "refund_id": refund_id_str}},
        )
        return ("ignored", [])

    if fully_refunded:
        # CARRY-FORWARD (Task 7 ledger contract): the hook zero-outs
        # budget_serves_total and pauses the campaign. No re-pay path from
        # paused/refunded is built here - that is a fresh checkout on a
        # fresh order (the partial-unique index on ad_orders excludes
        # 'refunded'). A PARTIAL refund deliberately does NOT fire this
        # hook - a goodwill part-refund must not pause a live campaign.
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
    plink_entity = _nested_entity(payload, "payload", "payment_link", "entity")
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


# ---------------------------------------------------------------------------
# M5 Task 12: GST invoice PDF sweep - runs after dunning in worker.py's tick.


def invoice_lines_from_order(order: AdOrder, invoice: Invoice) -> list[tuple[str, int]]:
    """Order.quote carries the itemized [label, amount_paise] pairs ads
    handed billing at checkout (`_quote_snapshot` in modules/ads/
    selfserve_router.py, built from modules/ads/pricing.py's Quote.lines -
    which sum to the quote's own subtotal by construction, so these lines
    foot to the invoice's taxable value);
    a campaign quoted before that field existed (or the bare 4-number
    reconstruction fallback in create_ad_order) has no `lines` key, so we
    fall back to one line for the whole taxable amount - never a KeyError,
    never a blank invoice body. Public (not `_`-prefixed): router.py's
    on-the-fly download-route render reuses this verbatim so the two
    renderers (sweep vs. GET) never drift on how lines are derived."""
    raw_lines = (order.quote or {}).get("lines")
    if raw_lines:
        return [(str(label), int(amount)) for label, amount in raw_lines]
    return [("Advertising services", invoice.taxable_paise or 0)]


async def run_invoice_pdf_sweep(
    session: AsyncSession, *, now: datetime
) -> tuple[int, list[PendingEvent]]:
    """Render + store the GST invoice PDF for every paid ad order whose
    invoice doesn't have one yet (`pdf_key IS NULL` is the work queue - this
    is the ONLY writer of `pdf_key`; the advertiser download route in
    router.py regenerates on the fly for a GET but never persists it).
    StorageError leaves the row untouched for a retry next tick. An
    unresolvable business owner or contact still gets its PDF stored (the
    download route needs `pdf_key` regardless of who can currently claim
    it) but no notify event - logged, not retried forever, since neither
    condition self-heals on its own."""
    rows = (
        await session.execute(
            select(Invoice, AdOrder)
            .join(AdOrder, Invoice.order_id == AdOrder.id)
            .where(
                Invoice.order_id.is_not(None),
                Invoice.status == "paid",
                Invoice.pdf_key.is_(None),
            )
            .order_by(Invoice.id)
            .limit(INVOICE_PDF_SWEEP_LIMIT)
        )
    ).all()
    if not rows:
        return (0, [])

    settings = get_settings()
    seller = (settings.gst_seller_name, settings.gst_seller_gstin, settings.gst_seller_address)
    processed = 0
    pending: list[PendingEvent] = []
    for invoice, order in rows:
        ref = await lookups.resolve_business(session, order.business_id)
        buyer_name = ref.name if ref is not None else ((order.quote or {}).get("campaign_name"))
        pdf_bytes = render_invoice_pdf(
            invoice_number=invoice.invoice_number or "",
            issued_on=(invoice.created_at or now).date(),
            seller=seller,
            buyer_name=str(buyer_name or "Advertiser"),
            buyer_gstin=order.buyer_gstin,
            lines=invoice_lines_from_order(order, invoice),
            taxable_paise=invoice.taxable_paise or 0,
            gst_paise=invoice.gst_paise or 0,
            total_paise=invoice.amount_paise,
        )
        key = f"invoices/{invoice.id.hex}.pdf"
        try:
            await storage.put_object(key, pdf_bytes, "application/pdf")
        except storage.StorageError as exc:
            logger.warning(
                "billing.invoice_pdf_store_failed",
                extra={
                    "extra_fields": {"invoice_id": str(invoice.id), "exc_type": type(exc).__name__}
                },
            )
            continue  # retry next tick - pdf_key stays NULL

        invoice.pdf_key = key
        processed += 1

        if ref is None or ref.owner_user_id is None:
            logger.warning(
                "billing.invoice_pdf_no_owner",
                extra={"extra_fields": {"invoice_id": str(invoice.id)}},
            )
            continue
        contact = await lookups.resolve_contact(session, ref.owner_user_id)
        if contact is None:
            logger.warning(
                "billing.invoice_pdf_no_contact",
                extra={"extra_fields": {"invoice_id": str(invoice.id)}},
            )
            continue
        payload: dict[str, Any] = {
            "user_id": str(ref.owner_user_id),
            "locale": contact.locale or "en",
            "email": contact.email,
            "phone": None,
            "vars": {
                "invoice_number": invoice.invoice_number or "",
                "total": f"{invoice.amount_paise / 100:,.2f}",
                "business_name": ref.name,
            },
            "attachment_key": key,
            "attachment_filename": f"{invoice.invoice_number}.pdf",
        }
        pending.append(("billing.ad_invoice", payload))

    await session.flush()
    return (processed, pending)
