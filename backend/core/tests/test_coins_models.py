"""ORM models mirror migration 0012 and round-trip through the DB."""
import uuid

import pytest
from sqlalchemy import select

from modules.coins.models import Balance, LedgerEntry, Rule

pytestmark = pytest.mark.asyncio


async def test_ledger_entry_roundtrips(db_session):
    uid = uuid.uuid4()
    db_session.add(LedgerEntry(
        user_id=uid, delta=100, reason_code="signup_complete",
        ref_type="rule", ref_id="signup_complete", idempotency_key=f"signup_complete:{uid}",
    ))
    await db_session.flush()
    got = await db_session.scalar(select(LedgerEntry).where(LedgerEntry.user_id == uid))
    assert got.delta == 100 and got.idempotency_key == f"signup_complete:{uid}"


async def test_seeded_rule_loads(db_session):
    rule = await db_session.get(Rule, "profile_100")
    assert rule.amount == 200 and rule.total_cap == 1 and rule.active is True


async def test_balance_defaults_zero(db_session):
    uid = uuid.uuid4()
    db_session.add(Balance(user_id=uid))
    await db_session.flush()
    got = await db_session.get(Balance, uid)
    assert got.balance == 0
