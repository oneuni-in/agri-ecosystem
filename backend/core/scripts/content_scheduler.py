"""The thing that actually runs the daily RSS pull. Run: python -m scripts.content_scheduler

WHY THIS EXISTS (A-U4b O3).
scripts/content_pull.py was written to be invoked by "a scheduler" and
nothing invoked it — the same failure class AG-A25 already named for the
mandi pull. The stakes are gentler here: RSS feeds carry a rolling
window, so a missed day is usually recoverable on the next run, where a
missed Agmarknet day is gone forever. But "usually" trims fast on a feed
that keeps ten entries, and a feed nobody pulls is not a slow section —
it is a dead one, silently frozen at whatever was last approved.

Shape follows scripts/mandi_scheduler.py, which follows
modules/coins/worker.py and modules/search/worker.py: one long-lived
container, `restart: unless-stopped`, no new infrastructure and no cron
daemon inside an image. The schedule lives in version control rather
than in a crontab on a host, where it would be invisible to the repo and
lost on a rebuild.

BEHAVIOUR
  - On startup, pulls immediately if today (IST) has no completed run —
    at ANY hour, not only after the slot. Gating the catch-up on the
    scheduled hour is the exact bug the mandi scheduler paid two days of
    data to learn (see its docstring): a dev container that boots during
    the working day and never survives to the slot pulls nothing, ever.
    This scheduler starts life without that gate.
  - Day-covered reads content.ingest_runs (one row per SOURCE per
    attempt). Unlike mandi, an `empty` outcome here means "feed reached,
    nothing new" — a COMPLETED pull, not "too early in the day" — so ok
    OR empty covers the day and there is no empty-recheck cooldown. A
    day whose only runs are failures is NOT covered: a failure is a
    reason to try again, never to stand down.
  - Then fires at settings.content_pull_hour_ist daily (morning IST —
    news accumulates overnight, and unlike Agmarknet the hour is
    convenience, not correctness), with same-day retries on failure.
    run_pull returns non-zero only when EVERY source failed — one
    publisher 403ing while the others deliver is a success and is not
    retried.
"""

import asyncio
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from modules.content.models import OUTCOME_EMPTY, OUTCOME_OK, IngestRun  # noqa: E402
from scripts.content_pull import run_pull  # noqa: E402
from settings import get_settings  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402
from shared.telemetry import (
    configure_logging,  # noqa: E402
    get_logger,  # noqa: E402
)

logger = get_logger(__name__)

# India Standard Time as a FIXED offset, mirroring
# modules/market_data/weather.py and for the same reason: IST is UTC+5:30
# year-round with no DST in its entire history, and ZoneInfo("Asia/Kolkata")
# needs the IANA database, which Windows dev boxes do not ship. Defined
# locally rather than imported from market_data — a content script has no
# business coupling itself to the weather module for two lines.
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(UTC).astimezone(IST)


# Outcomes that mean the pull COMPLETED. `empty` belongs here, unlike in
# the mandi scheduler: an empty content run proves the feed was reached
# and held nothing new — a real answer on a quiet news day — whereas an
# empty mandi run means the feed had not filled yet. fetch_failed and
# write_failed never cover a day.
_COMPLETED = (OUTCOME_OK, OUTCOME_EMPTY)


async def day_covered(session: AsyncSession, day: date) -> bool:
    """The pure decision: did this IST day see a completed pull?

    True if ANY source recorded an ok or empty run today — the pull is
    all-sources-per-invocation, so one completed row means the worker
    fired and finished. Failed runs never count.
    """
    start_utc = datetime.combine(day, datetime.min.time(), tzinfo=IST).astimezone(UTC)
    run = await session.scalar(
        select(IngestRun.id)
        .where(
            IngestRun.started_at >= start_utc,
            IngestRun.outcome.in_(_COMPLETED),
        )
        .limit(1)
    )
    return run is not None


async def _day_covered_safely(day: date) -> bool:
    """day_covered with the ledger-unreadable case decided towards pulling.

    A duplicate pull is free (items dedupe on the canonical URL); a
    skipped day can lose whatever a short feed has already trimmed.
    """
    try:
        async with get_sessionmaker()() as session:
            return await day_covered(session, day)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "content.scheduler_ledger_unreadable",
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
    attempts = max(1, settings.content_pull_retries)
    for attempt in range(1, attempts + 1):
        code = await run_pull()
        if code == 0:
            return
        if attempt < attempts:
            logger.warning(
                "content.pull_retry_scheduled",
                extra={"extra_fields": {"attempt": attempt, "of": attempts}},
            )
            await asyncio.sleep(settings.content_pull_retry_minutes * 60)
    logger.error(
        "content.pull_failed_all_attempts",
        # Every source failing at once smells like our side, not three
        # unrelated publishers. Tomorrow's run usually recovers the items
        # (feeds keep back-entries), but a short feed may have trimmed by
        # then — so this line is still the one worth alerting on.
        extra={"extra_fields": {"attempts": attempts}},
    )


async def _main() -> int:
    settings = get_settings()
    # Without this every logger.info below is dropped: configure_logging
    # runs in main.create_app, which a standalone script never touches, so
    # `docker logs` on this container would show NOTHING — indistinguishable
    # from a hung process on a job that sleeps for hours between pulls.
    # (The AG-A25 lesson; content_pull.py's __main__ documents it too.)
    # Logging config is global, so the pull this drives inherits it.
    configure_logging(settings.log_level)
    hour = settings.content_pull_hour_ist
    logger.info("content.scheduler_started", extra={"extra_fields": {"hour_ist": hour}})

    now = now_ist()
    # Catch-up on boot whenever today has no completed run — at any hour.
    # The mandi scheduler's ledger shows what an hour-gated catch-up buys
    # on a dev laptop: zero unattended pulls, ever. The ledger check keeps
    # a crash-looping container from hammering the publishers — a day with
    # one ok/empty run boots quietly.
    if not await _day_covered_safely(now.date()):
        logger.info(
            "content.scheduler_catchup",
            extra={"extra_fields": {"day": now.date().isoformat()}},
        )
        await _pull_with_retries()

    while True:
        now = now_ist()
        fire_at = _next_fire(now, hour)
        await asyncio.sleep(max(0.0, (fire_at - now).total_seconds()))
        await _pull_with_retries()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
