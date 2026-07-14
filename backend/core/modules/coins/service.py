"""Coins core ledger service (D13) - the ONLY writer of coins.ledger_entries
and coins.balances. AgriCoins are NOT money: no purchase, cash-out, or
transfer path exists here by design.

Concurrency + idempotency invariants:
- Single-credit is proven by the UNIQUE(idempotency_key) constraint, not by
  application logic. A duplicate insert is caught and the existing entry is
  returned unchanged.
- The per-user balances row is updated with a conditional UPDATE; its row lock
  serializes concurrent writers for the same user, so the materialized balance
  can never drift and (with the >= 0 guard + CHECK) can never go negative.
- record_entry never commits; the caller owns the transaction. The ledger
  insert runs inside a SAVEPOINT so a duplicate-key IntegrityError rolls back
  only that insert, leaving the caller's transaction usable.
"""

import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import rules
from modules.coins.models import Balance, LedgerEntry
from shared.pagination import Page, paginate


class InsufficientBalanceError(Exception):
    """A redeem/negative delta would take the balance below zero."""


async def record_entry(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    delta: int,
    reason_code: str,
    ref_type: str,
    ref_id: str | None,
    idempotency_key: str,
) -> LedgerEntry:
    if delta == 0:
        raise ValueError("delta must be non-zero")

    entry = LedgerEntry(
        user_id=user_id,
        delta=delta,
        reason_code=reason_code,
        ref_type=ref_type,
        ref_id=ref_id,
        idempotency_key=idempotency_key,
    )
    # One savepoint wraps the ledger insert AND the balance update so that a
    # rejected redeem (or a duplicate key) discards BOTH and never poisons the
    # caller's transaction. The savepoint is only released (kept) on success.
    sp = await session.begin_nested()
    try:
        session.add(entry)
        await session.flush()  # UNIQUE(idempotency_key) fires here on replay
    except IntegrityError:
        await sp.rollback()
        # DB-proven idempotency: the key already exists -> single credit only.
        existing = await session.scalar(
            select(LedgerEntry).where(LedgerEntry.idempotency_key == idempotency_key)
        )
        assert existing is not None
        return existing

    # Ensure a balance row, then apply the delta under its row lock. The guard
    # rejects a negative delta that would overdraw; 0 rows updated => reject.
    await session.execute(
        text(
            "INSERT INTO coins.balances (user_id, balance) VALUES (:u, 0) "
            "ON CONFLICT (user_id) DO NOTHING"
        ),
        {"u": user_id},
    )
    updated = await session.scalar(
        text(
            "UPDATE coins.balances SET balance = balance + :d "
            "WHERE user_id = :u AND balance + :d >= 0 RETURNING balance"
        ),
        {"u": user_id, "d": delta},
    )
    if updated is None:
        await sp.rollback()  # discard the ledger row too: rejection persists nothing
        raise InsufficientBalanceError(f"insufficient balance for user {user_id}")
    await sp.commit()
    return entry


async def redeem(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: int,
    reason_code: str,
    ref_id: str | None,
    idempotency_key: str,
) -> LedgerEntry:
    if amount <= 0:
        raise ValueError("redeem amount must be positive")
    return await record_entry(
        session,
        user_id=user_id,
        delta=-amount,
        reason_code=reason_code,
        ref_type="redeem",
        ref_id=ref_id,
        idempotency_key=idempotency_key,
    )


async def balance(session: AsyncSession, user_id: uuid.UUID) -> int:
    value = await session.scalar(select(Balance.balance).where(Balance.user_id == user_id))
    return int(value or 0)


async def history(
    session: AsyncSession, user_id: uuid.UUID, *, cursor: str | None, limit: int
) -> Page[LedgerEntry]:
    return await paginate(
        session,
        select(LedgerEntry).where(LedgerEntry.user_id == user_id),
        cursor=cursor,
        limit=limit,
    )


async def award(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    rule_code: str,
    ref_id: str | None,
    idempotency_key: str,
    now: datetime,
) -> LedgerEntry:
    """Rules-gated award - the ONLY sanctioned award path (no cap bypass)."""
    rule = await rules.load_active_rule(session, rule_code, now)
    await rules.check_numeric_caps(session, rule, user_id, now)
    return await record_entry(
        session,
        user_id=user_id,
        delta=rule.amount,
        reason_code=rule_code,
        ref_type="rule",
        ref_id=ref_id,
        idempotency_key=idempotency_key,
    )
