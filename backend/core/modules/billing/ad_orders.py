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
order is the only one anyone is ever shown a checkout_url for.
"""

import uuid
from typing import Any

import uuid6
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.models import AdOrder
from modules.billing.razorpay_client import RazorpayError
from settings import Settings
from shared import lookups

MAX_DESCRIPTION_LENGTH = 255


async def create_ad_order(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    campaign_id: uuid.UUID,
    buyer_gstin: str | None,
    client: Any,
    settings: Settings,
) -> tuple[AdOrder, str]:
    """Checkout. Returns (order, checkout_url). Server-side re-quote is the
    ONLY price - the client never supplies an amount (the route's
    AdOrderCreateIn has no such field, extra="forbid")."""
    ref = await lookups.resolve_campaign_billing(session, campaign_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Not Found")
    owner = await lookups.resolve_business(session, ref.business_id)
    if owner is None or owner.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Not Found")  # IDOR: not-yours==404
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
    # the stored price snapshot - it never re-derives GST.
    order_id = uuid6.uuid7()
    quote: dict[str, Any] = {
        "pricing_model": ref.pricing_model,
        "subtotal_paise": ref.subtotal_paise,
        "gst_paise": ref.gst_paise,
        "total_paise": ref.price_paise,
        "campaign_name": ref.name,
    }
    description = f"Milk.in ads: {ref.name}"[:MAX_DESCRIPTION_LENGTH]
    callback_url = f"{settings.console_base_url}/business/ads?paid={campaign_id}"
    try:
        remote = await client.create_payment_link(
            amount_paise=ref.price_paise,
            description=description,
            reference_id=str(order_id),
            callback_url=callback_url,
            notes={"campaign_id": str(campaign_id), "order_id": str(order_id)},
        )
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
        razorpay_plink_id=str(remote["id"]),
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

    return order, str(remote["short_url"])
