"""The thing that actually runs the daily pull. Run: python -m scripts.mandi_scheduler

WHY THIS EXISTS.
scripts/mandi_pull.py was written to be invoked by "a scheduler" and
nothing invoked it. The Agmarknet daily resource serves only the live
day (ADR-0012), so that was not a dormant feature waiting to be turned
on — it was silent, permanent, daily data loss with an honest-looking
explanation sitting on top of it ("the feed was quiet on Sunday").

Shape follows modules/coins/worker.py and modules/search/worker.py: one
long-lived container, `restart: unless-stopped`, no new infrastructure
and no cron daemon inside an image. The schedule lives in version
control rather than in a crontab on a host, where it would be invisible
to the repo and lost on a rebuild.

BEHAVIOUR
  - On startup, pulls immediately if today has no successful run yet —
    at ANY hour, not only after the slot. The first version gated the
    boot catch-up on `now.hour >= 19`, and the ledger shows what that
    bought: zero unattended pulls, ever. Every observed boot of the dev
    container was between 08:24 and 17:55 IST — a laptop's working day —
    so the catch-up never armed, and the process never survived to 19:00.
    Two whole days of Agmarknet data (18–19 Aug) are permanently gone to
    that gate. A morning pull captures a partial day, but the pull
    upserts on its natural key, so the 19:00 pull tops it up; partial
    beats nothing on a feed that serves only the live day.
  - Still fires at settings.mandi_pull_hour_ist (evening IST — the feed
    fills through the working day) regardless of a boot pull, for the
    top-up. The ledger check is what keeps restarts from re-pulling all
    day: one ok/empty run marks the day covered for CATCH-UP purposes,
    while the scheduled evening pull always runs. An `empty` run only
    stands catch-up down for EMPTY_RECHECK_HOURS — the feed being empty
    at 08:39 says nothing about 15:00.
  - Retries a failed pull within the same day (settings.mandi_pull_retries
    x mandi_pull_retry_minutes) instead of waiting for tomorrow. An empty
    day is not a failure and is not retried.
"""

import asyncio
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from modules.market_data.models import OUTCOME_EMPTY, OUTCOME_OK, IngestRun  # noqa: E402
from modules.market_data.weather import IST, now_ist  # noqa: E402
from scripts.mandi_pull import run_pull  # noqa: E402
from settings import get_settings  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402
from shared.telemetry import (
    configure_logging,  # noqa: E402
    get_logger,  # noqa: E402
)

logger = get_logger(__name__)


# An `empty` run proves the feed was reached, not that the day is covered:
# the very first ungated catch-up (2026-08-20 08:39 IST) got 0 records
# because Agmarknet genuinely holds nothing that early — mandis report
# through the working day. Treating that as "done" would immunise the whole
# day against catch-up, and a container rebooting at 15:00 would again be
# praying it survives to 19:00. So an empty run only suppresses catch-up
# for a cooldown, while an OK run covers the day. Three hours keeps a
# restart-happy laptop to a handful of API calls a day.
EMPTY_RECHECK_HOURS = 3


async def _day_covered(day: date, now_utc: datetime) -> bool:
    """Should the boot catch-up stand down for this IST day?

    Yes if the day has an OK run (data landed; the 19:00 loop still tops
    up), or an ok/empty run within the last EMPTY_RECHECK_HOURS (we asked
    recently; asking again now would learn nothing). A failed run never
    counts: it is a reason to try again, not to skip the day.
    """
    start_utc = datetime.combine(day, datetime.min.time(), tzinfo=IST).astimezone(UTC)
    recent_cutoff = now_utc - timedelta(hours=EMPTY_RECHECK_HOURS)
    try:
        async with get_sessionmaker()() as session:
            ok_today = await session.scalar(
                select(IngestRun.id)
                .where(
                    IngestRun.started_at >= start_utc,
                    IngestRun.outcome == OUTCOME_OK,
                )
                .limit(1)
            )
            if ok_today is not None:
                return True
            recent = await session.scalar(
                select(IngestRun.id)
                .where(
                    IngestRun.started_at >= max(start_utc, recent_cutoff),
                    IngestRun.outcome.in_((OUTCOME_OK, OUTCOME_EMPTY)),
                )
                .limit(1)
            )
        return recent is not None
    except Exception as exc:  # noqa: BLE001
        # If the ledger cannot be read, pull anyway. A duplicate pull is
        # free (the natural key upserts); a skipped day is not.
        logger.warning(
            "market.scheduler_ledger_unreadable",
            extra={"extra_fields": {"exc_type": type(exc).__name__}},
        )
        return False


def _next_fire(after: datetime, hour: int) -> datetime:
    """The next occurrence of `hour` IST strictly after `after` (IST)."""
    candidate = after.replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(days=1)
    return candidate


async def _pull_with_retries() -> None:
    settings = get_settings()
    attempts = max(1, settings.mandi_pull_retries)
    for attempt in range(1, attempts + 1):
        code = await run_pull()
        if code == 0:
            return
        if attempt < attempts:
            logger.warning(
                "market.pull_retry_scheduled",
                extra={"extra_fields": {"attempt": attempt, "of": attempts}},
            )
            await asyncio.sleep(settings.mandi_pull_retry_minutes * 60)
    logger.error(
        "market.pull_failed_all_attempts",
        # An un-pulled day is permanently unrecoverable, so this is the
        # line that deserves an alert channel, not the individual retries.
        extra={"extra_fields": {"attempts": attempts}},
    )


async def _main() -> int:
    settings = get_settings()
    # Without this every logger.info below is dropped: configure_logging
    # runs in main.create_app, which a standalone script never touches, so
    # `docker logs` on this container showed NOTHING — indistinguishable
    # from a hung process on a job that sleeps for hours between pulls.
    # (scripts/verify_audit_chain.py sets the precedent.) Logging config is
    # global, so the pull this drives inherits it.
    configure_logging(settings.log_level)
    hour = settings.mandi_pull_hour_ist
    logger.info("market.scheduler_started", extra={"extra_fields": {"hour_ist": hour}})

    now = now_ist()
    # Catch-up on boot whenever today has no successful run — at any hour.
    # The previous `now.hour >= hour` gate assumed the process would either
    # boot after the slot or live until it; on a dev laptop neither is true,
    # and the gate converted "restarted during the working day" into
    # permanent data loss (see BEHAVIOUR above). An early pull is a partial
    # snapshot the 19:00 top-up completes; the upsert makes running both
    # free, and the ledger keeps a crash-looping container from hammering
    # the API — a day with one ok/empty run boots quietly.
    if not await _day_covered(now.date(), datetime.now(UTC)):
        logger.info("market.scheduler_catchup", extra={"extra_fields": {"day": now.isoformat()}})
        await _pull_with_retries()

    while True:
        now = now_ist()
        fire_at = _next_fire(now, hour)
        await asyncio.sleep(max(0.0, (fire_at - now).total_seconds()))
        await _pull_with_retries()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
