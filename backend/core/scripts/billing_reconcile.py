"""Nightly billing reconciliation. Run: python -m scripts.billing_reconcile
(from backend/core). Exits 1 when local vs Razorpay state drifted so a
scheduler/CI marks the run failed and pages (coins_integrity precedent).
While billing_enabled is off it exits 0 immediately - dark launch means
zero live calls, including from cron.

M5 Task 11 (NN3): runs the ad-order ledger reconciliation alongside the
subscription/invoice check above - one run, one exit code, either drift
family fails it. `--days` bounds the ad-order window (default 3, comfortably
wider than one nightly cadence so a single missed/late run doesn't drop
orders out of scope before they're ever checked)."""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

from modules.billing.razorpay_client import get_client
from modules.billing.reconcile import reconcile_ad_orders, run_reconciliation
from shared.db import get_sessionmaker
from shared.flags import flag_enabled


async def _main(days: int) -> int:
    async with get_sessionmaker()() as session:
        if not await flag_enabled("billing_enabled", session=session):
            print("billing_enabled is off; skipping reconciliation")  # noqa: T201 - CLI output
            return 0
        client = get_client()
        mismatches = await run_reconciliation(session, client=client)
        since = datetime.now(UTC) - timedelta(days=days)
        ad_problems = await reconcile_ad_orders(session, client=client, since=since)
        await session.commit()
    total = mismatches + ad_problems
    if total:
        print(  # noqa: T201 - CLI output
            f"RECONCILE FAILED: {mismatches} subscription/invoice mismatch(es), "
            f"{ad_problems} ad-order ledger problem(s) - see billing.reconcile_mismatch/"
            "billing.ad_reconcile_* logs"
        )
    return 1 if total else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=3,
        help="ad-order reconciliation window: orders updated in the last N days (default 3)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(_parse_args().days)))
