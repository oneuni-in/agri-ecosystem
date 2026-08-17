"""Daily Agmarknet pull (A-U2 W2). Run: python -m scripts.mandi_pull

Fetches the day's published prices for the configured state and writes
them through the quality gate. Idempotent: re-running the same day
updates in place (0038's natural-key constraint), so a retry after a
partial failure is safe and a double-scheduled run is harmless.

Exits non-zero on a fetch failure so a scheduler marks the run failed;
an empty day is NOT a failure (see the scheduling note below). Kill
switch: MANDI_INGEST_ENABLED=false.

EVERY ATTEMPT IS RECORDED (ADR-0012, market.ingest_runs).
The source serves only the live day, so a day not captured is gone for
good — no later job can recover it. That makes an absence of price rows
permanently ambiguous unless the attempt itself was written down: a
quiet Sunday, a container that never started, and a failed fetch all
leave exactly the same trace in price_rows, which is none. The ledger
row is therefore written on every path, including the ones that fetch
nothing and the ones that fail.

SCHEDULING — WHY NOT 6:00 AM.
The spec suggested ~6:00 AM IST. Measured on 2026-08-16, the feed had 58
rows nationwide at 08:48 IST, from six states, none of them Tamil Nadu:
the resource is published progressively through the working day as each
mandi reports. A 6:00 AM pull would therefore capture yesterday's
stragglers and almost nothing of today. Run it in the EVENING (IST) so
the day is substantially complete, and re-running later is free.
scripts/mandi_scheduler.py is what actually runs it on a schedule.
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.market_data.agmarknet import (  # noqa: E402
    DAILY_RESOURCE,
    AgmarknetError,
    fetch_day,
)
from modules.market_data.alerts import dispatch_due_alerts  # noqa: E402
from modules.market_data.ingest import IngestResult, ingest_records  # noqa: E402
from modules.market_data.models import (  # noqa: E402
    OUTCOME_DISABLED,
    OUTCOME_EMPTY,
    OUTCOME_FETCH_FAILED,
    OUTCOME_NO_API_KEY,
    OUTCOME_OK,
    OUTCOME_WRITE_FAILED,
    IngestRun,
)
from settings import get_settings  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402
from shared.telemetry import configure_logging, get_logger  # noqa: E402

logger = get_logger(__name__)


async def _record(
    *,
    started_at: datetime,
    outcome: str,
    state_filter: str | None,
    result: IngestResult | None = None,
    error: str | None = None,
) -> None:
    """Write the ledger row. Best-effort by design: failing to record a
    run must not also lose the rows the run just wrote."""
    counts = result or IngestResult()
    try:
        async with get_sessionmaker()() as session:
            session.add(
                IngestRun(
                    source="agmarknet",
                    source_resource=DAILY_RESOURCE,
                    state_filter=state_filter,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    outcome=outcome,
                    fetched=counts.fetched,
                    written=counts.written,
                    quarantined=counts.quarantined,
                    skipped_uncurated=counts.skipped_uncurated,
                    newest_arrival_date=counts.newest_arrival_date,
                    error=error,
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — never mask the real outcome
        logger.warning(
            "market.ingest_run_unrecorded",
            extra={"extra_fields": {"outcome": outcome, "exc_type": type(exc).__name__}},
        )


async def run_pull() -> int:
    """One pull attempt. Returns a process exit code; records the run."""
    settings = get_settings()
    started_at = datetime.now(UTC)
    state = settings.mandi_ingest_state

    if not settings.mandi_ingest_enabled:
        # Recorded, not silent: a disabled kill switch is a perfectly good
        # explanation for a gap, but only if it was written down.
        await _record(started_at=started_at, outcome=OUTCOME_DISABLED, state_filter=state)
        return 0

    if not settings.data_gov_api_key:
        await _record(started_at=started_at, outcome=OUTCOME_NO_API_KEY, state_filter=state)
        print("data_gov_api_key is not set - nothing fetched")  # noqa: T201
        return 1

    try:
        records = await fetch_day(state=state)
    except AgmarknetError as exc:
        # A failed pull is not a data problem: the site keeps serving the
        # last ingested day with its own as-of stamp (honest degradation).
        # It IS a permanent hole in the series, which is why it is both
        # recorded and retried within the day.
        await _record(
            started_at=started_at,
            outcome=OUTCOME_FETCH_FAILED,
            state_filter=state,
            error=f"{type(exc).__name__}: {exc}",
        )
        print(f"agmarknet fetch failed: {exc}")  # noqa: T201
        return 1

    try:
        async with get_sessionmaker()() as session:
            result = await ingest_records(session, records)
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — the run must still be recorded
        await _record(
            started_at=started_at,
            outcome=OUTCOME_WRITE_FAILED,
            state_filter=state,
            error=f"{type(exc).__name__}: {exc}",
        )
        print(f"mandi write failed: {exc}")  # noqa: T201
        return 1

    # An empty day is a SUCCESSFUL run that found nothing — a fact about
    # the mandi (Sundays, holidays, a state that has not reported yet),
    # not a failure of ours. Conflating the two is exactly the ambiguity
    # the ledger exists to remove, so it gets its own outcome and a zero
    # exit code.
    outcome = OUTCOME_OK if result.fetched else OUTCOME_EMPTY
    await _record(started_at=started_at, outcome=outcome, state_filter=state, result=result)

    # AG-A16: digests go out AFTER the ingest has committed, so an alert can
    # only ever describe prices that are actually readable. Failing to
    # notify must not un-write the day's prices, so this is best-effort and
    # never changes the pull's exit code — the once-a-day latch means the
    # next run picks up anyone missed.
    try:
        async with get_sessionmaker()() as session:
            published = await dispatch_due_alerts(session)
            await session.commit()
        if published:
            print(f"price alerts: {published} digest(s) published")  # noqa: T201
    except Exception as exc:  # noqa: BLE001 — prices are already safe
        logger.warning(
            "market.price_alert_dispatch_failed",
            extra={"extra_fields": {"exc_type": type(exc).__name__}},
        )

    print(  # noqa: T201
        f"mandi pull: outcome={outcome} fetched={result.fetched} written={result.written}"
        f" quarantined={result.quarantined} skipped_uncurated={result.skipped_uncurated}"
    )
    return 0


if __name__ == "__main__":
    # Run by hand, nothing has configured logging yet (the scheduler does
    # it for the scheduled path). Without this the ingest's own counters
    # never reach the operator running it.
    configure_logging(get_settings().log_level)
    sys.exit(asyncio.run(run_pull()))
