"""M5 Task 5: the ads<->billing seam in shared.lookups (same dependency-
inversion precedent as register_principal_resolver / register_business_
resolver). Unregistered resolver/hook fail closed: None / no-op, never raise.
Pure asyncio - no DB needed, mirrors test_require_auth.py's _NO_SESSION stub."""

import uuid
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.lookups import (
    CampaignBillingRef,
    notify_campaign_payment,
    register_campaign_billing_resolver,
    register_campaign_payment_hook,
    reset_lookup_resolvers,
    resolve_campaign_billing,
)

pytestmark = pytest.mark.asyncio

_NO_SESSION = cast(AsyncSession, None)  # unit tests: stubs below ignore it


async def test_unregistered_billing_resolver_returns_none() -> None:
    reset_lookup_resolvers()
    assert await resolve_campaign_billing(_NO_SESSION, uuid.uuid4()) is None


async def test_unregistered_payment_hook_is_a_noop() -> None:
    reset_lookup_resolvers()
    # must not raise even though nothing is registered
    await notify_campaign_payment(_NO_SESSION, uuid.uuid4(), "paid")


async def test_registered_billing_resolver_round_trips() -> None:
    campaign_id = uuid.uuid4()
    business_id = uuid.uuid4()
    paid_at = datetime.now(UTC)
    ref = CampaignBillingRef(
        id=campaign_id,
        business_id=business_id,
        name="Kovai Mills Tier-3 push",
        status="active",
        pricing_model="cpm",
        price_paise=50000,
        subtotal_paise=42373,
        gst_paise=7627,
        paid_at=paid_at,
    )
    calls: list[tuple[AsyncSession, uuid.UUID]] = []

    async def resolver(session: AsyncSession, campaign_id: uuid.UUID) -> CampaignBillingRef | None:
        calls.append((session, campaign_id))
        return ref

    register_campaign_billing_resolver(resolver)

    result = await resolve_campaign_billing(_NO_SESSION, campaign_id)
    assert result == ref
    assert calls == [(_NO_SESSION, campaign_id)]


async def test_registered_payment_hook_round_trips() -> None:
    calls: list[tuple[AsyncSession, uuid.UUID, str]] = []

    async def hook(session: AsyncSession, campaign_id: uuid.UUID, event: str) -> None:
        calls.append((session, campaign_id, event))

    register_campaign_payment_hook(hook)
    campaign_id = uuid.uuid4()

    await notify_campaign_payment(_NO_SESSION, campaign_id, "paid")

    assert calls == [(_NO_SESSION, campaign_id, "paid")]


async def test_reset_clears_both_billing_resolver_and_payment_hook() -> None:
    async def resolver(session: AsyncSession, campaign_id: uuid.UUID) -> CampaignBillingRef | None:
        return CampaignBillingRef(
            id=campaign_id,
            business_id=uuid.uuid4(),
            name="x",
            status="active",
            pricing_model=None,
            price_paise=None,
            subtotal_paise=None,
            gst_paise=None,
            paid_at=None,
        )

    hook_calls: list[str] = []

    async def hook(session: AsyncSession, campaign_id: uuid.UUID, event: str) -> None:
        hook_calls.append(event)

    register_campaign_billing_resolver(resolver)
    register_campaign_payment_hook(hook)

    reset_lookup_resolvers()

    assert await resolve_campaign_billing(_NO_SESSION, uuid.uuid4()) is None
    await notify_campaign_payment(_NO_SESSION, uuid.uuid4(), "refunded")
    assert hook_calls == []
