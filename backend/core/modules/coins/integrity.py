"""Coins balance integrity (D13). Nightly: recompute per-user SUM(delta) vs
the stored materialized balance; ANY drift is logged, metered and alerted.
Read-only over the ledger; never mutates balances (corrections are compensating
entries decided by an operator)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins.models import Balance, LedgerEntry
from shared.events import publish
from shared.metrics import COINS_BALANCE_DRIFT
from shared.telemetry import get_logger

logger = get_logger(__name__)


async def find_drift(session: AsyncSession) -> list[tuple[uuid.UUID, int, int]]:
    """Per-user (user_id, stored_balance, recomputed_sum) for every user_id in
    the union of `balances` and `ledger_entries` where the two disagree.
    """
    sums: dict[uuid.UUID, int] = {}
    for user_id, total in await session.execute(
        select(LedgerEntry.user_id, func.sum(LedgerEntry.delta)).group_by(LedgerEntry.user_id)
    ):
        sums[user_id] = int(total)

    stored: dict[uuid.UUID, int] = {}
    for user_id, bal in await session.execute(select(Balance.user_id, Balance.balance)):
        stored[user_id] = int(bal)

    drift: list[tuple[uuid.UUID, int, int]] = []
    for user_id in set(sums) | set(stored):
        s = stored.get(user_id, 0)
        r = sums.get(user_id, 0)
        if s != r:
            drift.append((user_id, s, r))
    return drift


async def run_integrity_check(session: AsyncSession) -> int:
    """Recompute vs stored; log + meter + alert on ANY drift. Returns the
    number of drifting users. Never mutates balances.
    """
    drift = await find_drift(session)
    if not drift:
        logger.info("coins integrity: no drift")
        return 0
    for user_id, stored, recomputed in drift:
        logger.error(
            "coins integrity DRIFT",
            extra={
                "extra_fields": {
                    "user_id": str(user_id),
                    "stored": stored,
                    "recomputed": recomputed,
                }
            },
        )
        COINS_BALANCE_DRIFT.inc()
    await publish(
        "notify",
        "coins.balance_drift",
        {"count": len(drift), "user_ids": [str(u) for (u, _, _) in drift[:50]]},
    )
    return len(drift)
