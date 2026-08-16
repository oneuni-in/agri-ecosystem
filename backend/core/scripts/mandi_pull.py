"""Daily Agmarknet pull (A-U2 W2). Run: python -m scripts.mandi_pull

Fetches the day's published prices for the configured state and writes
them through the quality gate. Idempotent: re-running the same day
updates in place (0038's natural-key constraint), so a retry after a
partial failure is safe and a double-scheduled run is harmless.

Exits non-zero on a fetch failure so a scheduler marks the run failed;
an empty day is NOT a failure (see the scheduling note below). Kill
switch: MANDI_INGEST_ENABLED=false. Same shape as
scripts/geo_tier_nightly.py — no new scheduler.

SCHEDULING — WHY NOT 6:00 AM.
The spec suggested ~6:00 AM IST. Measured on 2026-08-16, the feed had 58
rows nationwide at 08:48 IST, from six states, none of them Tamil Nadu:
the resource is published progressively through the working day as each
mandi reports. A 6:00 AM pull would therefore capture yesterday's
stragglers and almost nothing of today. Run it in the EVENING (IST) so
the day is substantially complete, and re-running later is free.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.market_data.agmarknet import AgmarknetError, fetch_day  # noqa: E402
from modules.market_data.ingest import ingest_records  # noqa: E402
from settings import get_settings  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402


async def _main() -> int:
    settings = get_settings()
    if not settings.mandi_ingest_enabled:
        return 0
    if not settings.data_gov_api_key:
        print("data_gov_api_key is not set - nothing fetched")  # noqa: T201
        return 1

    try:
        records = await fetch_day(state=settings.mandi_ingest_state)
    except AgmarknetError as exc:
        # A failed pull is not a data problem: the site keeps serving the
        # last ingested day with its own as-of stamp (honest degradation).
        print(f"agmarknet fetch failed: {exc}")  # noqa: T201
        return 1

    async with get_sessionmaker()() as session:
        result = await ingest_records(session, records)
        await session.commit()

    print(  # noqa: T201
        f"mandi pull: fetched={result.fetched} written={result.written}"
        f" quarantined={result.quarantined} skipped_uncurated={result.skipped_uncurated}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
