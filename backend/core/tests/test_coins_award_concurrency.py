"""A-U4 W2 — concurrency on the AWARD path (money-path requirement).

`test_coins_storm.py` already proves no drift and no negative balance under
10k parallel operations, but every operation there carries a UNIQUE
idempotency key. The two races it cannot see are the ones that matter for an
idempotent, capped rules engine:

  1. THE SAME KEY, RACED. A redelivered event, a double-tapped button, two
     workers on the same stream entry — N concurrent awards carrying one key
     must produce exactly ONE ledger row and ONE balance increment.

  2. A NUMERIC CAP, RACED. `rules.check_numeric_caps` does SELECT COUNT then
     INSERT. That is a read-then-write against a value other transactions are
     changing, which is the textbook shape of a TOCTOU race — so it is worth
     knowing, with a test rather than an opinion, exactly how far past a cap
     concurrent awards can push.

Both use a real committing engine so writers genuinely contend on the
per-user balance row lock; an in-transaction test would prove nothing here.
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from modules.coins import service
from modules.coins.models import Balance, LedgerEntry, Rule

pytestmark = pytest.mark.asyncio


@pytest.mark.slow
async def test_same_idempotency_key_raced_credits_exactly_once(database_url: str) -> None:
    """The idempotency guarantee, under contention rather than in sequence."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    uid = uuid.uuid4()
    key = f"replay:{uid}"
    attempts = 50

    async def attempt() -> None:
        async with maker() as s:
            await service.record_entry(
                s,
                user_id=uid,
                delta=10,
                reason_code="storm",
                ref_type="rule",
                ref_id=None,
                idempotency_key=key,
            )
            await s.commit()

    try:
        # return_exceptions: a loser in the unique-key race may surface as an
        # integrity error, which is a CORRECT outcome. What must not happen is
        # a second row.
        await asyncio.gather(*(attempt() for _ in range(attempts)), return_exceptions=True)

        async with maker() as s:
            rows = await s.scalar(
                select(func.count())
                .select_from(LedgerEntry)
                .where(LedgerEntry.user_id == uid, LedgerEntry.idempotency_key == key)
            )
            balance = await s.scalar(select(Balance.balance).where(Balance.user_id == uid))

        assert rows == 1, f"{attempts} concurrent awards on one key wrote {rows} rows"
        assert balance == 10, f"balance {balance} != 10 after a raced replay"
    finally:
        await engine.dispose()


@pytest.mark.slow
async def test_numeric_cap_under_concurrency(database_url: str) -> None:
    """How far past a weekly cap can concurrent awards push?

    Each attempt carries a DISTINCT idempotency key (different review ids),
    so the unique index cannot help — only `check_numeric_caps` stands
    between the caller and an over-award, and it counts before it inserts.

    This test asserts the cap is not wildly exceeded and RECORDS the real
    behaviour. It is deliberately not a strict `== cap` assertion: if the
    read-then-write window does allow a small overshoot, that is a fact the
    money path's reviewer needs stated, not a test that fails intermittently
    in CI and gets marked flaky.
    """
    engine = create_async_engine(database_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    uid = uuid.uuid4()
    code = f"cap_race_{uuid.uuid4().hex[:8]}"
    cap = 5
    attempts = 40
    now = datetime.now(UTC)

    async with maker() as s:
        await s.execute(insert(Rule).values(code=code, amount=10, active=True, weekly_cap=cap))
        await s.commit()

    async def attempt(i: int) -> None:
        async with maker() as s:
            try:
                await service.award(
                    s,
                    user_id=uid,
                    rule_code=code,
                    ref_id=str(i),
                    idempotency_key=f"{code}:{uid}:{i}",
                    now=now,
                )
                await s.commit()
            except Exception:  # noqa: BLE001 — cap hit and race losers both land here
                await s.rollback()

    try:
        await asyncio.gather(*(attempt(i) for i in range(attempts)))

        async with maker() as s:
            awarded = await s.scalar(
                select(func.count())
                .select_from(LedgerEntry)
                .where(LedgerEntry.user_id == uid, LedgerEntry.reason_code == code)
            )
            balance = await s.scalar(select(Balance.balance).where(Balance.user_id == uid))

        # The invariants that must hold no matter how the race resolves:
        # the cap bounds the award count to something of the cap's order (not
        # all 40 getting through), and the balance always equals the ledger.
        assert awarded is not None and awarded >= 1
        assert awarded <= attempts
        assert balance == awarded * 10, (
            f"balance {balance} != ledger {awarded} x 10 — drift under cap contention"
        )
        # Before the per-user advisory lock in service.award this measured
        # 40/40 - the cap admitted every concurrent attempt. It is exact now,
        # and asserted exactly: a regression here is a money-path regression,
        # not a flake to widen a tolerance for.
        assert awarded == cap, (
            f"cap {cap} admitted {awarded} of {attempts} concurrent awards - "
            "award() is no longer serialized per user"
        )
        print(f"\n[money-path] weekly_cap={cap}, {attempts} concurrent -> awarded={awarded}")  # noqa: T201
    finally:
        async with maker() as s:
            await s.execute(Rule.__table__.delete().where(Rule.code == code))
            await s.commit()
        await engine.dispose()
