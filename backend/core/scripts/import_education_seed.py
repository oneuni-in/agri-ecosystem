"""Import the committed education seed bundle.

    cd backend/core
    python -m scripts.import_education_seed --dry-run
    python -m scripts.import_education_seed

Exit 0 = imported (or validated, under --dry-run). Exit 1 = contract
violations printed and nothing written.

CONNECTS WITH THE ADMIN URL, NOT THE RUNTIME ONE.

`education` grants app_rt SELECT and nothing else (0049, spec section 4),
so `get_sessionmaker()` — which builds from `settings.database_url`, the
app_rt identity — cannot write a single row here. This script builds its own
engine from `settings.database_admin_url`, the same way
`modules/ads/worker.py` does for its DDL. That is the read-only design
working: importing college data is an operator action with owner
credentials, not something the application can do.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from modules.education.seed_import import import_bundle  # noqa: E402
from scripts.education_seed_contract import SeedContractError  # noqa: E402
from settings import get_settings  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-dir", type=Path, default=_ROOT / "data" / "seeds" / "education")
    parser.add_argument("--geo-dir", type=Path, default=_ROOT / "data" / "geo")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    engine = create_async_engine(get_settings().database_admin_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            try:
                report = await import_bundle(
                    session, args.seed_dir, args.geo_dir, today=datetime.now(UTC).date()
                )
            except SeedContractError as exc:
                print(  # noqa: T201 - CLI output
                    f"CONTRACT VIOLATIONS ({len(exc.violations)}) - nothing imported:"
                )
                for violation in exc.violations:
                    print(f"  {violation}")  # noqa: T201 - CLI output
                await session.rollback()
                return 1

            for name in sorted(set(report.created) | set(report.updated)):
                print(  # noqa: T201 - CLI output
                    f"  {name:<24} created {report.created[name]:>4}  "
                    f"updated {report.updated[name]:>4}"
                )
            if args.dry_run:
                await session.rollback()
                print("DRY RUN - rolled back, nothing written")  # noqa: T201 - CLI output
            else:
                await session.commit()
                print("committed")  # noqa: T201 - CLI output
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    return asyncio.run(_main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
