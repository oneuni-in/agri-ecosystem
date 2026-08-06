"""Cross-module lookups by dependency inversion (D20).

import-linter's independence contract forbids modules importing each other,
so billing cannot call directory/identity code directly. Instead - exactly
like shared.security.register_principal_resolver (D09) - the OWNING module
registers a resolver here and main.create_app() wires it. The code that runs
is always the owning module's own; nothing here reads another module's
tables. Fail closed: unregistered resolvers answer None/empty, never raise.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class BusinessRef:
    id: uuid.UUID
    owner_user_id: uuid.UUID | None
    name: str


@dataclass(frozen=True, slots=True)
class NotifyContact:
    email: str | None
    locale: str | None


BusinessResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[BusinessRef | None]]
OwnedBusinessesResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[list[BusinessRef]]]
ContactResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[NotifyContact | None]]
# M1.5.E: directory answers "may this business be served/shown at all?"
# (status == 'active'); ads consumes it at serve time - the M3 seam.
ServableResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[bool]]
# M1.5.B: ads pauses an advertiser's active campaigns on disable, in the
# caller's transaction; returns the paused campaign ids for the audit row.
CampaignPauser = Callable[[AsyncSession, uuid.UUID], Awaitable[list[str]]]


@dataclass(frozen=True, slots=True)
class CampaignBillingRef:
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    status: str
    pricing_model: str | None
    price_paise: int | None  # None = unpriced (house/admin) - NOT billable
    subtotal_paise: int | None  # price decomposition: billing invoices need
    gst_paise: int | None  #   taxable vs GST without re-deriving (Task 9/10)
    paid_at: datetime | None
    # M5 Task 9 fast-follow: the itemized quote snapshot (line items + rates
    # + tier + multiplier + gst_rate_bp) ads persisted at quote time -
    # billing copies this verbatim into AdOrder.quote for invoice provenance
    # instead of reconstructing a bare 4-number dict. None for campaigns
    # quoted before this field existed, or house/admin campaigns.
    quote: dict[str, Any] | None


CampaignBillingResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[CampaignBillingRef | None]]
# M5: billing tells ads about a payment event so ads can flip the campaign's
# status; events are "paid" | "refunded". checkout's draft->pending_payment
# flip happens inside ads' own checkout-request path, not via this hook.
CampaignPaymentHook = Callable[[AsyncSession, uuid.UUID, str], Awaitable[None]]
# M5 Task 13 fast-follow: ads' campaign stats route reads the ledger's net
# retained money through this seam (never a mutable balance column) - the
# spec's own integration rule is "campaign spend reconciles against ledger,
# never against mutable state" (budget_serves_total gets overwritten to
# budget_serves_used as a serve-exhaustion trick on refund; deriving spend
# from that column alone silently reports 100% spend on a refunded
# campaign). None = the campaign has no ledger rows at all (never
# charged - house/unpaid), distinct from a real net of 0 (charged then
# fully refunded). Unregistered/fail-closed -> None, same as every other
# resolver here - the caller falls back to its own derived estimate.
CampaignChargedResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[int | None]]

_business_resolver: BusinessResolver | None = None
_owned_businesses_resolver: OwnedBusinessesResolver | None = None
_contact_resolver: ContactResolver | None = None
_servable_resolver: ServableResolver | None = None
_campaign_pauser: CampaignPauser | None = None
_campaign_billing_resolver: CampaignBillingResolver | None = None
_campaign_payment_hook: CampaignPaymentHook | None = None
_campaign_charged_resolver: CampaignChargedResolver | None = None


def register_business_resolver(resolver: BusinessResolver) -> None:
    global _business_resolver
    _business_resolver = resolver


def register_owned_businesses_resolver(resolver: OwnedBusinessesResolver) -> None:
    global _owned_businesses_resolver
    _owned_businesses_resolver = resolver


def register_contact_resolver(resolver: ContactResolver) -> None:
    global _contact_resolver
    _contact_resolver = resolver


def register_servable_resolver(resolver: ServableResolver) -> None:
    global _servable_resolver
    _servable_resolver = resolver


def register_campaign_pauser(pauser: CampaignPauser) -> None:
    global _campaign_pauser
    _campaign_pauser = pauser


def register_campaign_billing_resolver(resolver: CampaignBillingResolver) -> None:
    global _campaign_billing_resolver
    _campaign_billing_resolver = resolver


def register_campaign_payment_hook(hook: CampaignPaymentHook) -> None:
    global _campaign_payment_hook
    _campaign_payment_hook = hook


def register_campaign_charged_resolver(resolver: CampaignChargedResolver) -> None:
    global _campaign_charged_resolver
    _campaign_charged_resolver = resolver


def reset_lookup_resolvers() -> None:
    global _business_resolver, _owned_businesses_resolver, _contact_resolver
    global _servable_resolver, _campaign_pauser
    global _campaign_billing_resolver, _campaign_payment_hook, _campaign_charged_resolver
    _business_resolver = None
    _owned_businesses_resolver = None
    _contact_resolver = None
    _servable_resolver = None
    _campaign_pauser = None
    _campaign_billing_resolver = None
    _campaign_payment_hook = None
    _campaign_charged_resolver = None


async def resolve_business(session: AsyncSession, business_id: uuid.UUID) -> BusinessRef | None:
    if _business_resolver is None:
        return None
    return await _business_resolver(session, business_id)


async def resolve_owned_businesses(
    session: AsyncSession, owner_user_id: uuid.UUID
) -> list[BusinessRef]:
    if _owned_businesses_resolver is None:
        return []
    return await _owned_businesses_resolver(session, owner_user_id)


async def resolve_contact(session: AsyncSession, user_id: uuid.UUID) -> NotifyContact | None:
    if _contact_resolver is None:
        return None
    return await _contact_resolver(session, user_id)


async def is_servable(session: AsyncSession, business_id: uuid.UUID) -> bool:
    """Serve-time enforcement check (M1.5.E). FAIL CLOSED: no resolver or an
    unknown business means False - a suspended vendor's ads must never serve
    because wiring was missing."""
    if _servable_resolver is None:
        return False
    return await _servable_resolver(session, business_id)


async def pause_campaigns_for_business(session: AsyncSession, business_id: uuid.UUID) -> list[str]:
    if _campaign_pauser is None:
        return []
    return await _campaign_pauser(session, business_id)


async def resolve_campaign_billing(
    session: AsyncSession, campaign_id: uuid.UUID
) -> CampaignBillingRef | None:
    if _campaign_billing_resolver is None:
        return None
    return await _campaign_billing_resolver(session, campaign_id)


async def notify_campaign_payment(
    session: AsyncSession, campaign_id: uuid.UUID, event: str
) -> None:
    """M5 checkout/webhook -> ads hook. FAIL CLOSED: no resolver means the
    payment is silently dropped from ads' view - money is still recorded on
    the billing side, the campaign just stays pending, and reconcile surfaces
    the gap rather than either side raising mid-webhook."""
    if _campaign_payment_hook is None:
        return
    await _campaign_payment_hook(session, campaign_id, event)


async def resolve_campaign_charged(session: AsyncSession, campaign_id: uuid.UUID) -> int | None:
    """Net retained money for a campaign (SUM of billing's append-only
    ledger, charges positive/refunds negative). FAIL CLOSED: no resolver
    registered means None - the caller must treat that exactly like "no
    ledger rows found", i.e. fall back to its own derived estimate rather
    than trusting a possibly-unwired zero."""
    if _campaign_charged_resolver is None:
        return None
    return await _campaign_charged_resolver(session, campaign_id)
