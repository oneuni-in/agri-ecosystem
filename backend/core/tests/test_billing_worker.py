"""Worker tick: honors billing_worker_enabled and the billing_enabled flag
(flag off -> no reads, no Razorpay calls)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing import razorpay_client, worker
from modules.billing.models import AdOrder, Invoice, Subscription
from modules.billing.service import apply_charge_failed
from modules.directory.models import Business
from settings import get_settings
from shared.db import get_sessionmaker, reset_engine
from shared.flags import FeatureFlag, reset_flag_cache
from shared.lookups import (
    BusinessRef,
    NotifyContact,
    register_business_resolver,
    register_contact_resolver,
)
from tests.fixtures.billing import FakeRazorpay

pytestmark = pytest.mark.asyncio

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


async def test_tick_noop_when_worker_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BILLING_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    fake = FakeRazorpay()
    monkeypatch.setattr(razorpay_client, "get_client", lambda: fake)
    assert await worker.worker_tick(now=T0) == 0
    assert fake.calls == []


async def test_tick_noop_when_flag_off(
    db_session: AsyncSession, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D20 defense in depth: while `billing_enabled` is off the tick does
    NOTHING - no dunning transitions, no M5 invoice-PDF sweep, no Razorpay
    call, zero reads past the flag check.

    DATABASE_URL is repointed at the migrated TEST database (the same pattern
    test_tick_advances_due_dunning uses - see its docstring) because
    worker_tick opens its OWN session via get_sessionmaker(), which otherwise
    resolves to whatever DATABASE_URL the developer's environment carries:
    their real dev database. Without this, the assertion measures dev-DB
    contents rather than the flag-off contract - on a machine where dev
    `billing_enabled` is flipped on for manual QA the tick genuinely runs, the
    PDF sweep genuinely WRITES to that dev DB, and the return is the number of
    unswept paid invoices sitting there (the observed `assert 5 == 0`). The
    flag is also asserted/forced off explicitly here: this test's premise must
    be established, never inherited from ambient state."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    reset_engine()
    maker = get_sessionmaker()
    async with maker() as setup:
        flag = await setup.get(FeatureFlag, "billing_enabled")
        assert flag is not None
        flag.enabled = False
        await setup.commit()
    reset_flag_cache()

    fake = FakeRazorpay()
    monkeypatch.setattr(razorpay_client, "get_client", lambda: fake)
    assert await worker.worker_tick(now=T0) == 0
    assert fake.calls == []
    reset_flag_cache()


async def test_tick_advances_due_dunning(
    db_session: AsyncSession, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """worker_tick opens its own session via get_sessionmaker() - a real,
    separate connection from db_session's (which lives inside an outer
    transaction the conftest fixture always rolls back, never commits at the
    Postgres level, so a `db_session.commit()` alone stays invisible to any
    other connection - not just a stale-cache problem). Setup here therefore
    writes and commits through get_sessionmaker() too (same DATABASE_URL,
    same real-commit path the worker itself uses), and cleans up afterward
    since nothing rolls these rows back automatically. db_session is still
    requested to keep the migrated-DB fixture chain (database_url /
    _scratch_tables_ready) wired up, even though it does no writes here."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    reset_engine()
    maker = get_sessionmaker()

    business_id: uuid.UUID | None = None
    try:
        async with maker() as setup:
            flag = await setup.get(FeatureFlag, "billing_enabled")
            assert flag is not None
            flag.enabled = True
            business = Business(
                name="Kovai Mills",
                slug=f"kovai-{uuid.uuid4().hex[:8]}",
                owner_user_id=uuid.uuid4(),
                type="farm",
                primary_pincode="641001",
            )
            setup.add(business)
            await setup.flush()
            business_id = business.id
            sub = Subscription(business_id=business.id, tier="growth", razorpay_sub_id="sub_wrk")
            setup.add(sub)
            await setup.flush()
            await apply_charge_failed(setup, sub, now=T0, settings=get_settings())
            await setup.commit()
        reset_flag_cache()

        fake = FakeRazorpay()
        fake.subs["sub_wrk"] = {"id": "sub_wrk", "status": "halted", "current_end": None}
        monkeypatch.setattr(razorpay_client, "get_client", lambda: fake)
        processed = await worker.worker_tick(now=T0 + timedelta(hours=25))
        assert processed == 1
    finally:
        async with maker() as cleanup:
            flag = await cleanup.get(FeatureFlag, "billing_enabled")
            if flag is not None:
                flag.enabled = False
            if business_id is not None:
                await cleanup.execute(
                    delete(Subscription).where(Subscription.business_id == business_id)
                )
                await cleanup.execute(delete(Business).where(Business.id == business_id))
            await cleanup.commit()
        reset_flag_cache()


async def test_tick_also_sweeps_invoice_pdfs(
    db_session: AsyncSession,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    object_store: dict[str, bytes],
) -> None:
    """M5 Task 12: worker_tick runs the invoice-PDF sweep in the same tick,
    same commit+publish choreography, after dunning (same real-sessionmaker
    setup/cleanup pattern as test_tick_advances_due_dunning - see its
    docstring for why db_session.commit() alone would not be visible here)."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    reset_engine()
    maker = get_sessionmaker()

    business_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    async def _biz(session: AsyncSession, biz_id: uuid.UUID) -> BusinessRef | None:
        if biz_id == business_id:
            return BusinessRef(id=biz_id, owner_user_id=owner_id, name="Kovai Mills")
        return None

    async def _contact(session: AsyncSession, user_id: uuid.UUID) -> NotifyContact | None:
        return NotifyContact(email="owner@example.com", locale="en")

    register_business_resolver(_biz)
    register_contact_resolver(_contact)

    order_id: uuid.UUID | None = None
    try:
        async with maker() as setup:
            flag = await setup.get(FeatureFlag, "billing_enabled")
            assert flag is not None
            flag.enabled = True
            order = AdOrder(
                campaign_id=uuid.uuid4(),
                business_id=business_id,
                status="paid",
                subtotal_paise=100_000,
                gst_paise=18_000,
                total_paise=118_000,
                quote={"campaign_name": "Kharif push"},
                razorpay_plink_id=f"plink_{uuid.uuid4().hex[:8]}",
                razorpay_payment_id=f"pay_{uuid.uuid4().hex[:8]}",
            )
            setup.add(order)
            await setup.flush()
            order_id = order.id
            setup.add(
                Invoice(
                    order_id=order.id,
                    subscription_id=None,
                    amount_paise=118_000,
                    taxable_paise=100_000,
                    gst_paise=18_000,
                    status="paid",
                    invoice_number="MILK-26-27-000099",
                )
            )
            await setup.commit()
        reset_flag_cache()

        fake = FakeRazorpay()
        monkeypatch.setattr(razorpay_client, "get_client", lambda: fake)
        processed = await worker.worker_tick(now=T0)
        assert processed == 1  # dunning did nothing this tick; the sweep did

        async with maker() as verify:
            invoice = await verify.scalar(select(Invoice).where(Invoice.order_id == order_id))
            assert invoice is not None
            assert invoice.pdf_key is not None
            assert invoice.pdf_key in object_store
            assert object_store[invoice.pdf_key].startswith(b"%PDF")
    finally:
        async with maker() as cleanup:
            flag = await cleanup.get(FeatureFlag, "billing_enabled")
            if flag is not None:
                flag.enabled = False
            if order_id is not None:
                await cleanup.execute(delete(Invoice).where(Invoice.order_id == order_id))
                await cleanup.execute(delete(AdOrder).where(AdOrder.id == order_id))
            await cleanup.commit()
        reset_flag_cache()
