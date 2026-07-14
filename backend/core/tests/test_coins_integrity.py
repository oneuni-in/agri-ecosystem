"""Nightly integrity: recompute vs stored; ANY drift is detected + alerted."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import integrity, service

pytestmark = pytest.mark.asyncio


async def test_clean_ledger_no_drift(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await service.record_entry(
        db_session,
        user_id=uid,
        delta=100,
        reason_code="r",
        ref_type="rule",
        ref_id=None,
        idempotency_key=f"c:{uid}",
    )
    assert await integrity.find_drift(db_session) == []


async def test_injected_drift_is_detected(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await service.record_entry(
        db_session,
        user_id=uid,
        delta=100,
        reason_code="r",
        ref_type="rule",
        ref_id=None,
        idempotency_key=f"d:{uid}",
    )
    # corrupt the materialized balance directly (balances is not trigger-locked)
    await db_session.execute(
        text("UPDATE coins.balances SET balance = 999 WHERE user_id = :u"), {"u": uid}
    )
    drift = await integrity.find_drift(db_session)
    assert (uid, 999, 100) in drift


async def test_run_alerts_on_drift(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await service.record_entry(
        db_session,
        user_id=uid,
        delta=50,
        reason_code="r",
        ref_type="rule",
        ref_id=None,
        idempotency_key=f"a:{uid}",
    )
    await db_session.execute(
        text("UPDATE coins.balances SET balance = 7 WHERE user_id = :u"), {"u": uid}
    )
    with patch("modules.coins.integrity.publish", new=AsyncMock()) as pub:
        n = await integrity.run_integrity_check(db_session)
    assert n == 1 and pub.await_count == 1
    assert pub.await_args_list[0].args[1] == "coins.balance_drift"
