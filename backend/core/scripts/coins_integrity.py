"""Nightly coins integrity check. Run: python -m scripts.coins_integrity
(or `python scripts/coins_integrity.py` from backend/core). Exits non-zero if
drift is found, so a scheduler/CI marks the run failed and pages."""

import asyncio
import sys

from modules.coins.integrity import run_integrity_check
from shared.db import get_sessionmaker


async def _main() -> int:
    async with get_sessionmaker()() as session:
        drift = await run_integrity_check(session)
        await session.commit()
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
