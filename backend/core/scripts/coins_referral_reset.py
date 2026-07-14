"""Monthly referral cap observability hook (D13 ops).

The REFERRER_MONTHLY_CAP (modules.coins.referrals.REFERRER_MONTHLY_CAP) is
computed on the fly from `Referral.rewarded_at` timestamps - there is no
counter table to zero out. This script is therefore NOT a reset in the
mutating sense; it exists as the scheduled monthly hook and logs each
referrer's current-calendar-month rewarded-referral count for observability
(e.g. to spot a referrer riding the cap every month). It always exits 0.

Run: python -m scripts.coins_referral_reset (or `python
scripts/coins_referral_reset.py` from backend/core).

Never logs anything beyond the referrer_id UUID and a count - no PII.
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins.models import Referral
from modules.coins.referrals import month_start
from shared.db import get_sessionmaker
from shared.telemetry import get_logger

logger = get_logger(__name__)


async def monthly_reward_counts(
    session: AsyncSession, now: datetime
) -> list[tuple[uuid.UUID, int]]:
    """Per-referrer count of referrals rewarded since the start of `now`'s month."""
    rows = await session.execute(
        select(Referral.referrer_id, func.count())
        .where(Referral.rewarded_at >= month_start(now))
        .group_by(Referral.referrer_id)
    )
    return [(referrer_id, count) for referrer_id, count in rows.all()]


async def _main() -> int:
    now = datetime.now(UTC)
    async with get_sessionmaker()() as session:
        counts = await monthly_reward_counts(session, now)
    for referrer_id, count in counts:
        logger.info(
            "coins referral monthly count",
            extra={"extra_fields": {"referrer_id": str(referrer_id), "rewarded_count": count}},
        )
    logger.info(
        "coins_referral_reset: month observed, no mutation performed",
        extra={"extra_fields": {"referrer_count": len(counts)}},
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
