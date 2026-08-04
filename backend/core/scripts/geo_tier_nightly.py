"""Nightly pincode-tier recompute (M4). Run: python -m scripts.geo_tier_nightly

Recounts verified users per pincode, then reclassifies tiers (promote-only,
min-interval hysteresis). Exits non-zero on a failed sanity check so a
scheduler/CI marks the run failed and pages. Kill switch:
GEO_TIER_JOB_ENABLED=false. D12 events/cron pattern - no new scheduler.
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.identity.user_counts import verified_user_counts_by_pincode  # noqa: E402
from settings import get_settings  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402
from shared.geo.tiers import TierSanityError, classify_tiers  # noqa: E402


async def _main() -> int:
    if not get_settings().geo_tier_job_enabled:
        return 0
    async with get_sessionmaker()() as session:
        counts = await verified_user_counts_by_pincode(session)
        try:
            result = await classify_tiers(session, now=datetime.now(UTC), user_counts=counts)
        except TierSanityError as exc:
            print(f"pincode tier sanity check failed: {exc}")  # noqa: T201
            return 1
        await session.commit()
    print(  # noqa: T201
        f"pincode tiers: total={result.total} changed={result.changed}"
        f" skipped_hysteresis={result.skipped_hysteresis}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
