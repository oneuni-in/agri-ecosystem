"""Report education rows whose verification stamp has aged.

    cd backend/core
    python -m scripts.education_freshness            # older than 180 days
    python -m scripts.education_freshness --days 90

Dev-only by design (spec section 9): no worker, no UI state, no alerting. It
prints what needs rechecking before launch and exits 0 either way — this
reports, it does not gate. A stale stamp is not a broken row; it is a row
whose source should be opened again.

Reads with the RUNTIME credentials, unlike the importer. This only selects,
and app_rt holds SELECT on education.*, so there is no reason to hand a
read-only report owner credentials.

`institution_programmes` is listed alongside the three slugged tables because
its stamps are the ones most worth watching: a college's existence and its
current fee go stale at completely different rates, which is why that table
carries its own `source_url` and `last_verified_at` at all (spec section 4).
It has no slug, so it reports the institution's.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from modules.education.models import (  # noqa: E402
    Guide,
    Institution,
    InstitutionProgramme,
    StudentResource,
)
from shared.db import get_sessionmaker  # noqa: E402


async def _report[M: (Institution, StudentResource, Guide)](
    session: AsyncSession, model: type[M], label: str, cutoff: date
) -> int:
    """One table's stale rows, oldest first.

    A constrained type parameter rather than a loop over a heterogeneous tuple:
    unpacked from a tuple the element type collapses to Base, `last_verified_at`
    resolves against nothing, and the check silently covers no model at all.
    Here mypy re-checks the body once per model in the constraint list.
    """
    rows = (
        await session.scalars(
            select(model).where(model.last_verified_at < cutoff).order_by(model.last_verified_at)
        )
    ).all()
    for row in rows:
        print(f"  {label:<22} {row.slug:<44} {row.last_verified_at}")  # noqa: T201
    return len(rows)


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=180)
    args = parser.parse_args(argv)
    cutoff = datetime.now(UTC).date() - timedelta(days=args.days)

    total = 0
    async with get_sessionmaker()() as session:
        total += await _report(session, Institution, "institutions", cutoff)
        total += await _report(session, StudentResource, "student_resources", cutoff)
        total += await _report(session, Guide, "guides", cutoff)

        # Offerings have no slug of their own, so they report the college's.
        offerings = (
            await session.execute(
                select(Institution.slug, InstitutionProgramme.last_verified_at)
                .join(
                    InstitutionProgramme,
                    InstitutionProgramme.institution_id == Institution.id,
                )
                .where(InstitutionProgramme.last_verified_at < cutoff)
                .order_by(InstitutionProgramme.last_verified_at)
            )
        ).all()
        for slug, stamped in offerings:
            print(f"  {'offerings (fees/seats)':<22} {slug:<44} {stamped}")  # noqa: T201
        total += len(offerings)

    print(f"{total} row(s) stamped before {cutoff}")  # noqa: T201
    return 0


def main() -> int:
    return asyncio.run(_main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
