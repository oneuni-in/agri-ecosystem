"""Nightly local-vs-Razorpay drift detection (D20). State drift is the
threat: a webhook we never received, a manual dashboard change, a bug. Every
mismatch logs ids only + bumps billing_reconcile_mismatch_total; the script
wrapper exits non-zero so the scheduler pages."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.models import Subscription
from modules.billing.razorpay_client import RazorpayError
from shared.metrics import BILLING_RECONCILE_MISMATCH
from shared.telemetry import get_logger

logger = get_logger(__name__)

# Remote statuses consistent with each local status. Pre-first-charge
# (created/authenticated) maps to local active+NULL period (spec §3).
STATUS_EQUIV: dict[str, frozenset[str]] = {
    "active": frozenset({"active", "authenticated", "created"}),
    "past_due": frozenset({"pending", "halted"}),
}
PERIOD_TOLERANCE = timedelta(days=1)


async def run_reconciliation(session: AsyncSession, *, client: Any) -> int:
    """Compare every non-canceled local subscription against Razorpay.
    Returns the mismatch count. Caller gates on billing_enabled."""
    mismatches = 0
    subs = (
        await session.scalars(
            select(Subscription).where(
                Subscription.status != "canceled", Subscription.razorpay_sub_id.is_not(None)
            )
        )
    ).all()
    for sub in subs:
        assert sub.razorpay_sub_id is not None  # narrowed by the query
        try:
            remote = await client.fetch_subscription(sub.razorpay_sub_id)
        except RazorpayError as exc:
            logger.warning(
                "billing.reconcile_fetch_failed",
                extra={
                    "extra_fields": {
                        "subscription_id": str(sub.id),
                        "exc_type": type(exc).__name__,
                    }
                },
            )
            continue
        remote_status = str(remote.get("status"))
        consistent = remote_status in STATUS_EQUIV[sub.status]
        if consistent and sub.status == "active" and sub.current_period_end is not None:
            current_end = remote.get("current_end")
            if current_end:
                drift = abs(datetime.fromtimestamp(int(current_end), UTC) - sub.current_period_end)
                consistent = drift <= PERIOD_TOLERANCE
        if not consistent:
            mismatches += 1
            BILLING_RECONCILE_MISMATCH.inc()
            logger.warning(
                "billing.reconcile_mismatch",
                extra={
                    "extra_fields": {
                        "subscription_id": str(sub.id),
                        "local_status": sub.status,
                        "remote_status": remote_status,
                    }
                },
            )
    return mismatches
