# backend/core/modules/billing/router.py
"""Billing routes (D20) - the money path. 🔍 human line review required.

EVERYTHING here is gated by the billing_enabled DB flag at request time
(404 while dark - the flag flips without a deploy, unlike the env-mounted
MSG91 webhook). The webhook is public by design: Razorpay cannot log in.
Its gate is the HMAC signature over the raw body + event-id dedupe
(replay = one effect). Bodies are never logged."""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing import razorpay_client
from modules.billing.ad_orders import create_ad_order, invoice_lines_from_order
from modules.billing.invoice_pdf import render_invoice_pdf
from modules.billing.models import AdOrder, Invoice, PaymentEvent, Subscription
from modules.billing.sanitize import scrub_payload
from modules.billing.schemas import (
    AdOrderCreateIn,
    AdOrderOut,
    AdOrderPage,
    InvoicePage,
    MySubscriptionOut,
    SubscriptionCreateIn,
    SubscriptionCreateOut,
    ad_order_out,
    invoice_out,
    subscription_out,
    tier_list,
)
from modules.billing.service import process_webhook_event, publish_pending
from modules.billing.tiers import TIERS, plan_id_for
from settings import get_settings
from shared import storage
from shared.db import get_session
from shared.flags import flag_enabled
from shared.lookups import resolve_business, resolve_campaign_billing, resolve_owned_businesses
from shared.metrics import BILLING_WEBHOOK_REJECTED
from shared.pagination import InvalidCursorError, paginate
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

router = SecureRouter(prefix="/billing", tags=["billing"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _require_flag(session: AsyncSession) -> None:
    """flag off -> this surface does not exist (404, never 403)."""
    if not await flag_enabled("billing_enabled", session=session):
        raise HTTPException(status_code=404, detail="Not Found")


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal  # set by require_auth (shared.security)
    return uuid.UUID(str(principal.user_id))


@router.post("/webhook/razorpay", public=True)
async def razorpay_webhook(request: Request, session: SessionDep) -> dict[str, str]:
    await _require_flag(session)
    body = await request.body()
    secret = get_settings().razorpay_webhook_secret
    signature = request.headers.get("x-razorpay-signature", "")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not secret or not signature or not hmac.compare_digest(expected, signature):
        BILLING_WEBHOOK_REJECTED.labels(reason="signature").inc()
        raise HTTPException(status_code=400, detail="invalid signature")

    event_id = request.headers.get("x-razorpay-event-id", "")
    if not event_id:
        BILLING_WEBHOOK_REJECTED.labels(reason="missing_event_id").inc()
        raise HTTPException(status_code=400, detail="missing event id")
    # A6b-1: dedupe on a hash of the SIGNED body, never the unsigned
    # x-razorpay-event-id header. Razorpay signs only the body, so an attacker
    # who captures one valid (body, signature) can re-POST it with a fresh
    # event-id and still pass the signature check above; keying replay on the
    # header would let that replay re-run the state machine (e.g. flip a
    # past_due sub back to active with no real payment). The body hash is a
    # tamper-proof idempotency key — Razorpay resends the identical body (same
    # hash) on its own retries, so legitimate one-effect semantics are preserved.
    dedupe_key = hashlib.sha256(body).hexdigest()
    duplicate = await session.scalar(
        select(PaymentEvent.id).where(PaymentEvent.provider_event_id == dedupe_key)
    )
    if duplicate is not None:
        return {"status": "duplicate"}  # replay: one effect (unique index backstops races)

    try:
        payload = json.loads(body)
    except ValueError as exc:
        BILLING_WEBHOOK_REJECTED.labels(reason="malformed").inc()
        raise HTTPException(status_code=400, detail="malformed body") from exc
    if not isinstance(payload, dict):
        BILLING_WEBHOOK_REJECTED.labels(reason="malformed").inc()
        raise HTTPException(status_code=400, detail="malformed body")

    event_type = str(payload.get("event") or "")
    outcome, pending = await process_webhook_event(
        session,
        event_type=event_type,
        payload=payload,
        now=datetime.now(UTC),
        settings=get_settings(),
    )
    session.add(
        PaymentEvent(
            provider_event_id=dedupe_key,
            event_type=event_type,
            payload=scrub_payload(payload),
            outcome=outcome,
        )
    )
    # capture happened inside process_webhook_event; commit, then best-effort
    # publish (D16 choreography).
    try:
        await session.commit()
    except IntegrityError:
        # lost a concurrent-duplicate-delivery race: the unique
        # provider_event_id index is the arbiter, and the whole tx
        # (including the state transitions above) rolled back with it - so
        # one-effect still holds. Do not publish; the winning delivery's
        # commit already did.
        return {"status": "duplicate"}
    await publish_pending(pending)
    return {"status": "ok"}


@router.post("/subscriptions", status_code=201)
async def create_subscription(
    body: SubscriptionCreateIn, request: Request, session: SessionDep
) -> SubscriptionCreateOut:
    await _require_flag(session)
    user_id = _principal_user_id(request)
    if body.tier not in TIERS:
        raise HTTPException(status_code=422, detail="unknown tier")
    ref = await resolve_business(session, body.business_id)
    if ref is None or ref.owner_user_id != user_id:
        # not-yours == not-found: ownership must not be an oracle
        raise HTTPException(status_code=404, detail="business not found")
    live = await session.scalar(
        select(Subscription).where(
            Subscription.business_id == body.business_id, Subscription.status != "canceled"
        )
    )
    if live is not None:
        raise HTTPException(status_code=409, detail="subscription already exists")
    plan_id = plan_id_for(body.tier, get_settings())
    if not plan_id:
        raise HTTPException(status_code=503, detail="billing not configured")
    remote = await razorpay_client.get_client().create_subscription(
        plan_id=plan_id, notes={"business_id": str(body.business_id)}
    )
    sub = Subscription(
        business_id=body.business_id, tier=body.tier, razorpay_sub_id=str(remote["id"])
    )
    session.add(sub)
    # local status is `active` with current_period_end NULL until the first
    # subscription.charged webhook - the 3-state enum has no pre-charge state
    # by design (see the D20 spec §3); reconciliation treats the pair
    # (remote created/authenticated, local active+NULL) as consistent.
    try:
        await session.commit()
    except IntegrityError as exc:
        # lost a create race: the partial unique index (one live sub per
        # business) is the arbiter - same answer as the pre-check
        raise HTTPException(status_code=409, detail="subscription already exists") from exc
    # the remote Razorpay sub created above is orphaned for the race loser -
    # benign, since reconciliation is no-charge-before-checkout and the
    # customer never opens the loser's checkout URL.
    return SubscriptionCreateOut(
        subscription=subscription_out(sub), checkout_url=remote.get("short_url")
    )


@router.get("/subscription")
async def my_subscription(request: Request, session: SessionDep) -> MySubscriptionOut:
    await _require_flag(session)
    user_id = _principal_user_id(request)
    owned = await resolve_owned_businesses(session, user_id)
    for ref in owned:
        sub = await session.scalar(
            select(Subscription).where(
                Subscription.business_id == ref.id, Subscription.status != "canceled"
            )
        )
        if sub is not None:
            return MySubscriptionOut(
                subscription=subscription_out(sub), business_name=ref.name, tiers=tier_list()
            )
    return MySubscriptionOut(
        subscription=None,
        business_name=owned[0].name if owned else None,
        tiers=tier_list(),
    )


@router.get("/invoices")
async def my_invoices(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: int = 20,
) -> InvoicePage:
    await _require_flag(session)
    user_id = _principal_user_id(request)
    owned_ids = [ref.id for ref in await resolve_owned_businesses(session, user_id)]
    if not owned_ids:
        return InvoicePage(items=[], next_cursor=None)
    query = (
        select(Invoice)
        .join(Subscription, Invoice.subscription_id == Subscription.id)
        .where(Subscription.business_id.in_(owned_ids))
    )
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit, descending=True)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return InvoicePage(
        items=[invoice_out(invoice) for invoice in page.items], next_cursor=page.next_cursor
    )


# ---------------------------------------------------------------------------
# M5 Task 9: ad-order checkout (advertiser self-serve campaigns)


@router.post("/ad-orders", status_code=201)
async def create_order(body: AdOrderCreateIn, request: Request, session: SessionDep) -> AdOrderOut:
    await _require_flag(session)
    user_id = _principal_user_id(request)
    order = await create_ad_order(
        session,
        user_id=user_id,
        campaign_id=body.campaign_id,
        buyer_gstin=body.buyer_gstin,
        client=razorpay_client.get_client(),
        settings=get_settings(),
        now=datetime.now(UTC),
    )
    await session.commit()
    return ad_order_out(order)


AdOrderLimitQuery = Annotated[int, Query(ge=1, le=100)]


@router.get("/ad-orders")
async def list_orders(
    campaign_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: AdOrderLimitQuery = 20,
) -> AdOrderPage:
    """Owner-scoped, newest-first - the wizard's post-checkout status poll.
    Not-yours (or unknown campaign) is 404, never 403 (IDOR: no oracle)."""
    await _require_flag(session)
    user_id = _principal_user_id(request)
    ref = await resolve_campaign_billing(session, campaign_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Not Found")
    owner = await resolve_business(session, ref.business_id)
    if owner is None or owner.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Not Found")
    query = select(AdOrder).where(AdOrder.campaign_id == campaign_id)
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit, descending=True)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    # Task 12 review carry-forward: one bulk lookup for every order's
    # invoice (at most `limit` paid orders per page) rather than N+1 -
    # most orders on a page have no invoice at all (only 'paid' does).
    order_ids = [order.id for order in page.items]
    invoices_by_order: dict[uuid.UUID, Invoice] = {}
    if order_ids:
        invoice_rows = (
            await session.scalars(select(Invoice).where(Invoice.order_id.in_(order_ids)))
        ).all()
        invoices_by_order = {inv.order_id: inv for inv in invoice_rows if inv.order_id is not None}
    return AdOrderPage(
        items=[ad_order_out(order, invoices_by_order.get(order.id)) for order in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/ad-invoices/{invoice_id}/pdf")
async def download_ad_invoice_pdf(
    invoice_id: uuid.UUID, request: Request, session: SessionDep
) -> Response:
    """Task 12 review carry-forward: the advertiser's own copy of their GST
    invoice PDF. Private (billing_enabled-gated, owner-checked) - never the
    same as the public-read product-media prefix. Read-only: a missing
    `pdf_key` (the worker sweep hasn't reached this invoice yet) renders on
    the fly here but deliberately does NOT persist it - only
    ad_orders.run_invoice_pdf_sweep ever writes `pdf_key`, so a GET can
    never race the sweep's own storage write."""
    await _require_flag(session)
    user_id = _principal_user_id(request)
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None or invoice.order_id is None:
        raise HTTPException(status_code=404, detail="Not Found")
    order = await session.get(AdOrder, invoice.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Not Found")
    owner = await resolve_business(session, order.business_id)
    if owner is None or owner.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Not Found")  # IDOR: not-yours==404

    if invoice.pdf_key:
        try:
            pdf_bytes = await storage.get_object(invoice.pdf_key)
        except storage.StorageError as exc:
            raise HTTPException(status_code=404, detail="Not Found") from exc
    else:
        settings = get_settings()
        pdf_bytes = render_invoice_pdf(
            invoice_number=invoice.invoice_number or "",
            issued_on=(invoice.created_at or datetime.now(UTC)).date(),
            seller=(
                settings.gst_seller_name,
                settings.gst_seller_gstin,
                settings.gst_seller_address,
            ),
            buyer_name=owner.name,
            buyer_gstin=order.buyer_gstin,
            lines=invoice_lines_from_order(order, invoice),
            taxable_paise=invoice.taxable_paise or 0,
            gst_paise=invoice.gst_paise or 0,
            total_paise=invoice.amount_paise,
        )
    filename = f"{invoice.invoice_number or invoice.id.hex}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )
