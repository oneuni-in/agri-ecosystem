"""Execute due DPDP erasures. Run: python -m scripts.dpdp_erasure_job

Walks erasure requests whose grace window has elapsed, re-checks every
module's holds at THAT moment (a dispute opened during the grace still stops
the deletion), erases what is clear and marks the rest held for a human.

Same shape as scripts/geo_tier_nightly.py - no new scheduler, a kill switch,
and a non-zero exit so a failed run is visible rather than silent. Erasure is
irreversible, so the job commits once per tick and reports what it did.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import wire_dependencies  # noqa: E402
from modules.identity.dpdp_service import execute_due  # noqa: E402
from settings import get_settings  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402


async def _main() -> int:
    if not get_settings().dpdp_erasure_job_enabled:
        print("dpdp erasure job disabled")  # noqa: T201
        return 0
    # WITHOUT this the registry is empty, every module's hold goes unasked,
    # and "nobody objected" reads the same as "nobody was asked". That is not
    # hypothetical: the first run of this job erased an account that owned
    # five live businesses. shared.dpdp also fails closed on an empty
    # registry now; this is the other half.
    wire_dependencies()
    async with get_sessionmaker()() as session:
        result = await execute_due(session)
        await session.commit()
    print(  # noqa: T201
        f"dpdp erasures: considered={result['considered']} "
        f"executed={len(result['executed'])} held={len(result['held'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
