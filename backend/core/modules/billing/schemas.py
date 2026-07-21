"""Pydantic shapes for the billing routes (D20). Amounts stay integer paise
end-to-end; the console formats for display."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from modules.billing.models import Invoice, Subscription
from modules.billing.tiers import TIERS


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
