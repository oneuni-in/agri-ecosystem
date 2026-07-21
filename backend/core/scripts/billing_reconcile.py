"""Nightly billing reconciliation. Run: python -m scripts.billing_reconcile
(from backend/core). Exits 1 when local vs Razorpay state drifted so a
scheduler/CI marks the run failed and pages (coins_integrity precedent).
While billing_enabled is off it exits 0 immediately - dark launch means
zero live calls, including from cron."""

import asyncio
import sys

from modules.billing.razorpay_client import get_client
from modules.billing.reconcile import run_reconciliation
from shared.db import get_sessionmaker
from shared.flags import flag_enabled


async def _main() -> int:
    async with get_sessionmaker()() as session:
        if not await flag_enabled("billing_enabled", session=session):
            print("billing_enabled is off; skipping reconciliation")  # noqa: T201 - CLI output
            return 0
        mismatches = await run_reconciliation(session, client=get_client())
        await session.commit()
    if mismatches:
        print(  # noqa: T201 - CLI output
            f"RECONCILE FAILED: {mismatches} mismatch(es) - see billing.reconcile_mismatch logs"
        )
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
