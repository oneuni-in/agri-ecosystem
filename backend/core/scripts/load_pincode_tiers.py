"""Load population + classify tiers for the configured database.

    python scripts/load_pincode_tiers.py [--data-dir data/geo]

One command = load + classify = zero manual intervention (NN1). Uses
settings.database_url (override with the DATABASE_URL environment
variable). Exits non-zero (no commit) if the distribution fails sanity
checks (TierSanityError).
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.db import get_sessionmaker  # noqa: E402
from shared.geo.loader import load_pincode_population  # noqa: E402
from shared.geo.tiers import TierSanityError, classify_tiers  # noqa: E402


async def _run(data_dir: Path) -> int:
    async with get_sessionmaker()() as session:
        count = await load_pincode_population(session, data_dir)
        try:
            result = await classify_tiers(session, now=datetime.now(UTC))
        except TierSanityError as exc:
            print(f"tier sanity check failed: {exc}")  # noqa: T201 - CLI output
            return 1
        await session.commit()
    print(  # noqa: T201 - CLI output
        f"loaded {count} pincode populations from {data_dir}; "
        f"classified {result.total} rows, {result.changed} changed, "
        f"{result.skipped_hysteresis} skipped (hysteresis)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "geo",
    )
    return asyncio.run(_run(parser.parse_args().data_dir))


if __name__ == "__main__":
    sys.exit(main())
