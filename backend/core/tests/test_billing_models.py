"""Billing ORM models round-trip against the 0021 schema; tier vocabulary."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.models import Invoice, PaymentEvent, Subscription
from modules.billing.tiers import TIERS, plan_id_for
from settings import get_settings

pytestmark = pytest.mark.asyncio


async def test_subscription_roundtrip(db_session: AsyncSession) -> None:
    sub = Subscription(business_id=uuid.uuid4(), tier="growth")
    db_session.add(sub)
    await db_session.flush()
    loaded = await db_session.scalar(select(Subscription).where(Subscription.id == sub.id))
    assert loaded is not None
    assert loaded.status == "active"
    assert loaded.dunning_attempt == 0
    assert loaded.current_period_end is None


async def test_invoice_and_payment_event_roundtrip(db_session: AsyncSession) -> None:
    sub = Subscription(business_id=uuid.uuid4(), tier="pro")
    db_session.add(sub)
    await db_session.flush()
    db_session.add(
        Invoice(subscription_id=sub.id, amount_paise=149900, razorpay_invoice_id="inv_1")
    )
    db_session.add(
        PaymentEvent(provider_event_id="evt_1", event_type="ping", payload={}, outcome="ignored")
    )
    await db_session.flush()
    invoice = await db_session.scalar(select(Invoice).where(Invoice.subscription_id == sub.id))
    assert invoice is not None and invoice.currency == "INR" and invoice.status == "issued"


def test_tier_vocabulary_and_plan_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    assert set(TIERS) == {"growth", "pro"}
    assert all(tier.monthly_price_paise > 0 for tier in TIERS.values())
    settings = get_settings()
    assert plan_id_for("growth", settings) == ""  # unconfigured until KYC clears
    monkeypatch.setenv("RAZORPAY_PLAN_ID_GROWTH", "plan_abc")
    get_settings.cache_clear()
    assert plan_id_for("growth", get_settings()) == "plan_abc"


def test_dunning_settings_defaults() -> None:
    settings = get_settings()
    assert settings.dunning_retry_hours == "24,72,168"
    assert settings.dunning_grace_days == 7
    assert settings.billing_worker_enabled is True
