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
  - Wakes at settings.mandi_pull_hour_ist (evening IST — the feed fills
    through the working day; see mandi_pull's scheduling note).
  - On startup, pulls immediately IF today has no successful run yet.
    A container restarting at 20:05 must not skip the 19:00 slot, because
    tomorrow cannot recover today. The ledger is what makes that check
    possible without re-pulling on every restart.
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


async def _ran_today(day: date) -> bool:
    """Has a pull already completed for this IST day?

    Only 'ok' and 'empty' count: those are runs that actually reached the
    feed and learned what it held. A failed run is not a reason to skip
    the day — it is a reason to try again.
    """
    start_utc = datetime.combine(day, datetime.min.time(), tzinfo=IST).astimezone(UTC)
    try:
        async with get_sessionmaker()() as session:
            found = await session.scalar(
                select(IngestRun.id)
                .where(
                    IngestRun.started_at >= start_utc,
                    IngestRun.outcome.in_((OUTCOME_OK, OUTCOME_EMPTY)),
                )
                .limit(1)
            )
        return found is not None
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
    # Catch-up on boot: a restart after the day's slot must not silently
    # skip the day.
    if now.hour >= hour and not await _ran_today(now.date()):
        logger.info("market.scheduler_catchup", extra={"extra_fields": {"day": now.isoformat()}})
        await _pull_with_retries()

    while True:
        now = now_ist()
        fire_at = _next_fire(now, hour)
        await asyncio.sleep(max(0.0, (fire_at - now).total_seconds()))
        await _pull_with_retries()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
