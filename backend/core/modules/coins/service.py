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
    now: datetime | None = None,
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
    if now is not None:
        # award() passes the caller's logical `now` through so the ledger row
        # (and therefore rules.check_numeric_caps's weekly/daily window math,
        # which reads created_at back) is consistent with the same clock the
        # rest of the rules engine uses - not Postgres' real wall-clock
        # server_default, which would desync from a redelivered/backfilled
        # event's logical time. Other callers (redeem, admin adjust) omit
        # `now` and keep the unchanged server_default now() behavior.
        entry.created_at = now
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


def _user_lock_key(user_id: uuid.UUID) -> int:
    """A stable per-user bigint for pg_advisory_xact_lock.

    The top 64 bits of the UUID, mapped into signed range. Collisions between
    two different users are astronomically unlikely and, more importantly,
    harmless: a collision costs those two users a moment of mutual exclusion
    on their own awards, never a wrong balance.
    """
    return (user_id.int >> 64) - (1 << 63)


async def award(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    rule_code: str,
    ref_id: str | None,
    idempotency_key: str,
    now: datetime,
) -> LedgerEntry:
    """Rules-gated award - the ONLY sanctioned award path (no cap bypass).

    SERIALIZED PER USER, and that is a correctness fix rather than a
    precaution. `check_numeric_caps` counts existing ledger rows and then
    inserts one; without a lock those two steps race, and every concurrent
    transaction reads the same pre-insert count. Measured before this lock
    existed: a weekly_cap of 5 admitted ALL 40 concurrent awards
    (tests/test_coins_award_concurrency.py). The unique idempotency key
    cannot help here - each attempt legitimately carries a different key
    (different review ids), so the only thing standing between a user and an
    over-award is this count, and the count has to be serialized to mean
    anything.

    A transaction-scoped advisory lock is the right shape: it needs no row to
    exist (a first-ever award has no balance row to lock), it is released
    automatically on commit or rollback, and it serializes only the awards of
    ONE user - concurrent awards to different users are unaffected.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _user_lock_key(user_id)})
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
        now=now,
    )
