"""Worker tick: honors billing_worker_enabled and the billing_enabled flag
(flag off -> no reads, no Razorpay calls)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing import razorpay_client, worker
from modules.billing.models import Subscription
from modules.billing.service import apply_charge_failed
from modules.directory.models import Business
from settings import get_settings
from shared.db import get_sessionmaker, reset_engine
from shared.flags import FeatureFlag, reset_flag_cache
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
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRazorpay()
    monkeypatch.setattr(razorpay_client, "get_client", lambda: fake)
    assert await worker.worker_tick(now=T0) == 0
    assert fake.calls == []


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
