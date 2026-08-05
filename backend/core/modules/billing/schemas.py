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


class AdOrderPage(BaseModel):
    items: list[AdOrderOut]
    next_cursor: str | None


def ad_order_out(order: AdOrder) -> AdOrderOut:
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
    )


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
