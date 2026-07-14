"""DoD non-negotiable: 10k parallel award/redeem on ONE user -> exact final
balance, zero drift, zero negative. Uses a real committing engine so writers
actually contend on the per-user balance row lock."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from modules.coins import service
from modules.coins.models import Balance, LedgerEntry

pytestmark = pytest.mark.asyncio

N = 10_000
CONCURRENCY = 32  # bound simultaneous connections; asyncio queues the rest


@pytest.mark.slow
async def test_storm_no_drift_no_negative(database_url: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    uid = uuid.uuid4()
    sem = asyncio.Semaphore(CONCURRENCY)
    succeeded_delta = 0
    lock = asyncio.Lock()

    async def op(i: int) -> None:
        nonlocal succeeded_delta
        # deterministic mix: 60% awards (+10), 40% redeems (-5); unique keys
        is_award = (i % 5) < 3
        delta, amount, key = (10, None, f"aw:{uid}:{i}") if is_award else (None, 5, f"rd:{uid}:{i}")
        async with sem, maker() as s:
            try:
                if is_award:
                    await service.record_entry(
                        s,
                        user_id=uid,
                        delta=10,
                        reason_code="storm",
                        ref_type="rule",
                        ref_id=None,
                        idempotency_key=key,
                    )
                else:
                    await service.redeem(
                        s,
                        user_id=uid,
                        amount=5,
                        reason_code="storm",
                        ref_id=None,
                        idempotency_key=key,
                    )
                await s.commit()
                async with lock:
                    succeeded_delta += 10 if is_award else -5
            except service.InsufficientBalanceError:
                await s.rollback()

    try:
        await asyncio.gather(*(op(i) for i in range(N)))

        async with maker() as s:
            stored = await s.scalar(select(Balance.balance).where(Balance.user_id == uid))
            recomputed = await s.scalar(
                select(func.coalesce(func.sum(LedgerEntry.delta), 0)).where(
                    LedgerEntry.user_id == uid
                )
            )
            entry_count = await s.scalar(
                select(func.count()).select_from(LedgerEntry).where(LedgerEntry.user_id == uid)
            )
        assert stored is not None
        assert stored == succeeded_delta, "materialized balance drifted from successful ops"
        assert stored == recomputed, "materialized balance drifted from ledger sum"
        assert stored >= 0, "balance went negative"
        assert entry_count is not None and entry_count <= N  # rejected redeems left no rows
    finally:
        # The ledger is delete-protected and the test uses a unique throwaway
        # user, so there is nothing to clean up; the agri_test DB is dropped and
        # recreated once per session (conftest.database_url).
        await engine.dispose()
