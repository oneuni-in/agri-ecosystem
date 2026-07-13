"""Core ledger service: idempotency (DB-proven), atomic redeem, balance, history."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import service
from modules.coins.models import LedgerEntry

pytestmark = pytest.mark.asyncio


async def _count(session: AsyncSession, user_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(LedgerEntry).where(LedgerEntry.user_id == user_id)
        )
        or 0
    )


async def test_award_then_balance(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await service.record_entry(
        db_session,
        user_id=uid,
        delta=100,
        reason_code="signup_complete",
        ref_type="rule",
        ref_id="signup_complete",
        idempotency_key=f"s:{uid}",
    )
    assert await service.balance(db_session, uid) == 100


async def test_same_idempotency_key_credits_once(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    key = f"once:{uid}"
    e1 = await service.record_entry(
        db_session,
        user_id=uid,
        delta=100,
        reason_code="r",
        ref_type="rule",
        ref_id=None,
        idempotency_key=key,
    )
    e2 = await service.record_entry(
        db_session,
        user_id=uid,
        delta=100,
        reason_code="r",
        ref_type="rule",
        ref_id=None,
        idempotency_key=key,
    )
    assert e1.id == e2.id
    assert await _count(db_session, uid) == 1
    assert await service.balance(db_session, uid) == 100


async def test_redeem_success(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await service.record_entry(
        db_session,
        user_id=uid,
        delta=100,
        reason_code="r",
        ref_type="rule",
        ref_id=None,
        idempotency_key=f"a:{uid}",
    )
    await service.redeem(
        db_session,
        user_id=uid,
        amount=30,
        reason_code="spend",
        ref_id=None,
        idempotency_key=f"rd:{uid}",
    )
    assert await service.balance(db_session, uid) == 70


async def test_redeem_to_exactly_zero(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await service.record_entry(
        db_session,
        user_id=uid,
        delta=30,
        reason_code="r",
        ref_type="rule",
        ref_id=None,
        idempotency_key=f"az:{uid}",
    )
    await service.redeem(
        db_session,
        user_id=uid,
        amount=30,
        reason_code="spend",
        ref_id=None,
        idempotency_key=f"rdz:{uid}",
    )
    assert await service.balance(db_session, uid) == 0
    assert await _count(db_session, uid) == 2


async def test_redeem_insufficient_raises_and_persists_nothing(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await service.record_entry(
        db_session,
        user_id=uid,
        delta=20,
        reason_code="r",
        ref_type="rule",
        ref_id=None,
        idempotency_key=f"a2:{uid}",
    )
    with pytest.raises(service.InsufficientBalanceError):
        await service.redeem(
            db_session,
            user_id=uid,
            amount=50,
            reason_code="spend",
            ref_id=None,
            idempotency_key=f"rd2:{uid}",
        )
    assert await service.balance(db_session, uid) == 20
    assert await _count(db_session, uid) == 1  # the failed redeem left no row


async def test_history_is_keyset_paginated(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    for i in range(3):
        await service.record_entry(
            db_session,
            user_id=uid,
            delta=10,
            reason_code="r",
            ref_type="rule",
            ref_id=None,
            idempotency_key=f"h:{uid}:{i}",
        )
    page = await service.history(db_session, uid, cursor=None, limit=2)
    assert len(page.items) == 2 and page.next_cursor is not None
    page2 = await service.history(db_session, uid, cursor=page.next_cursor, limit=2)
    assert len(page2.items) == 1 and page2.next_cursor is None
