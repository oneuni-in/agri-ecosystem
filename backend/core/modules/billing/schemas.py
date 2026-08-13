"""Pydantic shapes for the billing routes (D20/M5). Amounts stay integer
paise end-to-end; the console formats for display."""

import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from modules.billing.models import AdOrder, Invoice, Subscription
from modules.billing.tiers import TIERS

_GSTIN_RE = re.compile(r"^[0-9A-Z]{15}$")


class SubscriptionCreateIn(BaseModel):
    business_id: uuid.UUID
    tier: str


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    tier: str
    status: str
    current_period_end: datetime | None


class SubscriptionCreateOut(BaseModel):
    subscription: SubscriptionOut
    checkout_url: str | None


class TierOut(BaseModel):
    key: str
    display_name: str
    monthly_price_paise: int


class MySubscriptionOut(BaseModel):
    subscription: SubscriptionOut | None
    business_name: str | None
    tiers: list[TierOut]


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount_paise: int
    currency: str
    status: str
    period_start: datetime | None
    period_end: datetime | None
    created_at: datetime


class InvoicePage(BaseModel):
    items: list[InvoiceOut]
    next_cursor: str | None


class AdOrderCreateIn(BaseModel):
    """extra="forbid" is the wire-contract price-tampering guard: a client
    that sends `total_paise` (or any other amount field) is rejected
    outright rather than silently ignored - modules/billing/ad_orders.py
    is the ONLY source of the charged amount."""

    model_config = ConfigDict(extra="forbid")

    campaign_id: uuid.UUID
    buyer_gstin: Annotated[str, Field(pattern=_GSTIN_RE.pattern)] | None = None


class AdOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    status: str
    total_paise: int
    checkout_url: str | None = None
    # Task 12 review carry-forward: a paid order's invoice was otherwise
    # invisible to the advertiser (GET /billing/invoices only inner-joins
    # Subscription). invoice_id is what the console needs to build the
    # /billing/ad-invoices/{id}/pdf download link; has_pdf is a cheap
    # "is it ready yet" hint (the download route regenerates on the fly
    # regardless, so this is UI sugar, not a correctness gate).
    invoice_id: uuid.UUID | None = None
    invoice_number: str | None = None
    has_pdf: bool = False


class AdOrderPage(BaseModel):
    items: list[AdOrderOut]
    next_cursor: str | None


def ad_order_out(order: AdOrder, invoice: Invoice | None = None) -> AdOrderOut:
    # money-path review fast-follow: the link is persisted on the order now
    # (razorpay_short_url), not just handed back once on the create response
    # - a GET refresh (the wizard's status poll) can show it again. Only
    # while `created` (still awaiting payment): once paid/failed/expired/
    # refunded there is nothing left to check out.
    checkout_url = order.razorpay_short_url if order.status == "created" else None
    return AdOrderOut(
        id=order.id,
        campaign_id=order.campaign_id,
        status=order.status,
        total_paise=order.total_paise,
        checkout_url=checkout_url,
        invoice_id=invoice.id if invoice is not None else None,
        invoice_number=invoice.invoice_number if invoice is not None else None,
        has_pdf=bool(invoice is not None and invoice.pdf_key),
    )


# --- U3 payments read surface (DISPLAY ONLY) ------------------------------
#
# The admin console reads the append-only ad-revenue ledger and the raw
# Razorpay webhook log. `amount_display` is formatted server-side so the UI
# never does money arithmetic (U3: no computed-in-the-UI money figures). There
# is no `signature_verified` column — a PaymentEvent only PERSISTS after the
# webhook's HMAC check passes (a bad signature 400s before any insert), so a
# logged event IS a signature-verified one; the flag is derived, always True.


def format_paise(paise: int, currency: str = "INR") -> str:
    """Signed paise → a display string (e.g. -2500 → '-₹25.00'). Formatting,
    not computation — the stored value is shown, never re-derived."""
    symbol = "₹" if currency == "INR" else f"{currency} "
    sign = "-" if paise < 0 else ""
    rupees, paise_part = divmod(abs(paise), 100)
    return f"{sign}{symbol}{rupees:,}.{paise_part:02d}"


class PaymentLedgerRowOut(BaseModel):
    id: uuid.UUID
    entry_type: str  # ad_charge | ad_refund
    amount_display: str
    amount_paise: int
    currency: str
    campaign_id: uuid.UUID | None
    business_id: uuid.UUID
    razorpay_payment_id: str | None
    created_at: datetime


class PaymentLedgerPage(BaseModel):
    items: list[PaymentLedgerRowOut]
    next_cursor: str | None


class PaymentEventRowOut(BaseModel):
    id: uuid.UUID
    provider: str
    event_type: str
    provider_event_id: str
    outcome: str
    # Derived, always True for a persisted event (see module note above).
    signature_verified: bool
    created_at: datetime


class PaymentEventPage(BaseModel):
    items: list[PaymentEventRowOut]
    next_cursor: str | None


def tier_list() -> list[TierOut]:
    return [
        TierOut(
            key=tier.key,
            display_name=tier.display_name,
            monthly_price_paise=tier.monthly_price_paise,
        )
        for tier in TIERS.values()
    ]


def subscription_out(sub: Subscription) -> SubscriptionOut:
    return SubscriptionOut.model_validate(sub)


def invoice_out(invoice: Invoice) -> InvoiceOut:
    return InvoiceOut.model_validate(invoice)
