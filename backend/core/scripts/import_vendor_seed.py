"""D27 bulk import: load data/seeds/coimbatore/*.csv into the directory.

    cd backend/core
    python -m scripts.import_vendor_seed            # real import + publish
    python -m scripts.import_vendor_seed --dry-run  # validate + report, rollback

Idempotent: reruns skip existing (name, primary_pincode) matches. Creates
OWNERLESS businesses (claimable via the D16 flow). Publishes fat-event
snapshots after commit so the D19 search worker indexes them (worker must
be running; scripts/reindex_search.py is the recovery path).
This is a careful one-off loader, NOT the D63 pipeline.
"""

import argparse
import asyncio
from pathlib import Path

from modules.directory.seed_import import SeedContractError, import_seed, load_bundle
from shared.db import get_sessionmaker
from shared.events import publish


async def run(seed_dir: Path, *, dry_run: bool) -> int:
    try:
        bundle = load_bundle(seed_dir)
    except SeedContractError as exc:
        print(f"CONTRACT VIOLATIONS - nothing imported:\n{exc}")  # noqa: T201 - CLI output
        return 1
    print(f"bundle: {len(bundle)} businesses from {seed_dir}")  # noqa: T201

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        report = await import_seed(session, bundle)
        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    for outcome in report.outcomes:
        print(f"  {outcome.action:8} {outcome.ref}")  # noqa: T201
    print(  # noqa: T201
        f"{'DRY RUN - rolled back' if dry_run else 'imported'}: "
        f"{report.created} created, {report.skipped} skipped"
    )

    if not dry_run and report.event_payloads:
        try:
            for event_type, payload in report.event_payloads:
                await publish("directory", event_type, payload)
            print(f"published {len(report.event_payloads)} search events")  # noqa: T201
        except Exception as exc:  # noqa: BLE001 - rows are committed; index is recoverable
            print(f"(publish failed - run scripts.reindex_search: {exc})")  # noqa: T201
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-dir", type=Path, default=Path("data/seeds/coimbatore"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.seed_dir, dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
