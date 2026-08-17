"""Curated RSS pull for the content engine. Run: python -m scripts.content_pull

Reads every ENABLED row in `content.sources` and writes new articles as
`pending`. Nothing this script does can publish anything — approving is a
human action behind `content.publish` in the CMS. Re-running is free:
items dedupe on the normalised canonical URL, so a second run the same
day writes nothing and records a run with a high `duplicates` count.

EVERY ATTEMPT IS RECORDED (ADR-0012, content.ingest_runs) — the
market_data lesson applies unchanged here: a quiet news day, a dead
container and a 403 from a publisher all leave the same trace in
`content.items`, which is none.

Unlike the mandi pull this is NOT racing a vanishing source: RSS feeds
carry a rolling window, so a missed day is usually recoverable on the
next run. It is still recorded, because "usually" is doing real work in
that sentence — a feed that trims to ten entries loses history fast.

Exit code is non-zero only if EVERY source failed to fetch. One
publisher being down is not a failed run when the others delivered.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.content.ingest import ingest_all  # noqa: E402
from modules.content.models import (  # noqa: E402
    OUTCOME_FETCH_FAILED,
    OUTCOME_WRITE_FAILED,
)
from settings import get_settings  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402
from shared.telemetry import configure_logging, get_logger  # noqa: E402

logger = get_logger(__name__)

_FAILURES = (OUTCOME_FETCH_FAILED, OUTCOME_WRITE_FAILED)


async def run_pull() -> int:
    """One pass over the curated sources. Returns a process exit code."""
    async with get_sessionmaker()() as session:
        results = await ingest_all(session)
        # ingest_all writes the run rows in this session; commit once so a
        # crash mid-loop cannot leave items without their ledger rows.
        await session.commit()

    if not results:
        print("content pull: no enabled sources")  # noqa: T201
        return 0

    for slug, result in results.items():
        print(  # noqa: T201
            f"  {slug}: outcome={result.outcome} fetched={result.fetched}"
            f" written={result.written} duplicates={result.duplicates}"
            f" skipped={result.skipped}" + (f" error={result.error}" if result.error else "")
        )
        logger.info(
            "content.ingest_run",
            extra={
                "extra_fields": {
                    "source": slug,
                    "outcome": result.outcome,
                    "written": result.written,
                    "duplicates": result.duplicates,
                }
            },
        )

    written = sum(r.written for r in results.values())
    failed = sum(1 for r in results.values() if r.outcome in _FAILURES)
    print(  # noqa: T201
        f"content pull: {len(results)} source(s), {written} new item(s) PENDING review,"
        f" {failed} failed"
    )
    # Partial success is success: one publisher 403ing must not mask the
    # fact that the other two delivered.
    return 1 if failed == len(results) else 0


if __name__ == "__main__":
    # Standalone scripts never ran configure_logging (the AG-A25 lesson):
    # without it, `docker logs` on a job that mostly sleeps shows nothing
    # at all, which is indistinguishable from a hang.
    configure_logging(get_settings().log_level)
    sys.exit(asyncio.run(run_pull()))
