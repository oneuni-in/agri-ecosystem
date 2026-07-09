"""Load the committed geo snapshot into the configured database.

    python scripts/load_geo.py [--data-dir data/geo]

Idempotent: upserts on lgd_code / pincode. Uses settings.database_url
(override with the DATABASE_URL environment variable).
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.db import get_sessionmaker  # noqa: E402
from shared.geo.loader import load_geo  # noqa: E402


async def _run(data_dir: Path) -> None:
    async with get_sessionmaker()() as session:
        counts = await load_geo(session, data_dir)
        await session.commit()
    print(  # noqa: T201 - CLI output
        f"loaded {counts.states} states, {counts.districts} districts, "
        f"{counts.pincodes} pincodes from {data_dir}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "geo",
    )
    asyncio.run(_run(parser.parse_args().data_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
