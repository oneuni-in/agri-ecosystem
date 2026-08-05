"""Nightly local-vs-Razorpay drift detection (D20). State drift is the
threat: a webhook we never received, a manual dashboard change, a bug.
Compares subscriptions and invoice paid-status. Every mismatch logs ids
only + bumps billing_reconcile_mismatch_total; the script wrapper exits
non-zero so the scheduler pages.

M5 Task 11 (NN3 - non-negotiable): `reconcile_ad_orders` extends the same
pattern to the append-only ad-revenue ledger (billing.ledger_entries,
Task 9/10) - the invariant is that the ledger sum for every paid/refunded
ad_order must equal exactly what Razorpay actually captured/refunded for
that order's payment. Unlike the subscription/invoice checks above (status
equivalence), this is an exact-amount comparison: any paise of drift is
reportable, because this ledger is money already recognized as revenue."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.models import AdOrder, BillingLedgerEntry, Invoice, Subscription
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

    invoices = (
        await session.scalars(
            select(Invoice).where(
                Invoice.status != "void", Invoice.razorpay_invoice_id.is_not(None)
            )
        )
    ).all()
    for inv in invoices:
        assert inv.razorpay_invoice_id is not None  # narrowed by the query
        try:
            remote = await client.fetch_invoice(inv.razorpay_invoice_id)
        except RazorpayError as exc:
            logger.warning(
                "billing.reconcile_fetch_failed",
                extra={
                    "extra_fields": {
                        "invoice_id": str(inv.id),
                        "exc_type": type(exc).__name__,
                    }
                },
            )
            continue
        remote_status = str(remote.get("status"))
        if (inv.status == "paid") != (remote_status == "paid"):
            mismatches += 1
            BILLING_RECONCILE_MISMATCH.inc()
            logger.warning(
                "billing.reconcile_invoice_mismatch",
                extra={
                    "extra_fields": {
                        "invoice_id": str(inv.id),
                        "local_status": inv.status,
                        "remote_status": remote_status,
                    }
                },
            )
    return mismatches


async def reconcile_ad_orders(session: AsyncSession, *, client: Any, since: datetime) -> int:
    """M5 Task 11 (NN3): the ad-revenue ledger must sum to EXACTLY what
    Razorpay captured/refunded - a paise of drift is reportable. Returns the
    total problem count (drift + fetch failures) so a caller that only cares
    about "was this reconcile clean" can gate on a single int; the two kinds
    are still logged/counted under distinct event names so ops can tell a
    real mismatch apart from "we couldn't check".

    Scope: every ad_order with `updated_at >= since` in:
    - status paid|refunded (must have been captured): ledger sum for the
      order must equal `payment.amount - payment.amount_refunded` exactly,
      AND `payment.amount` must equal the order's own `total_paise` (catches
      both a missed webhook and a manually-tampered ledger row that beat the
      append-only trigger via a superuser connection - the ledger-vs-order
      and ledger-vs-Razorpay checks collapse into the same comparison here).
    - status failed with a payment id set (Task 10's amount_mismatch
      forensics path): normally has ZERO ledger rows, but if Razorpay
      reports that payment as actually `captured`, money was taken and
      nothing was ever recorded - reportable so ops can refund it.

    Plus an orphan check, unscoped by order status: any ledger row (created
    since `since`) with no matching order (order_id NULL, or - defensively,
    though the FK should make this unreachable in practice - pointing at a
    row that no longer resolves) is drift; a ledger entry must always be
    attributable to an order."""
    problems = 0

    live_orders = (
        await session.scalars(
            select(AdOrder).where(
                AdOrder.status.in_(("paid", "refunded")),
                AdOrder.updated_at >= since,
                AdOrder.razorpay_payment_id.is_not(None),
            )
        )
    ).all()
    for order in live_orders:
        assert order.razorpay_payment_id is not None  # narrowed by the query
        try:
            payment = await client.fetch_payment(order.razorpay_payment_id)
        except RazorpayError as exc:
            problems += 1
            logger.warning(
                "billing.ad_reconcile_fetch_failed",
                extra={"extra_fields": {"order_id": str(order.id), "exc_type": type(exc).__name__}},
            )
            continue

        ledger_sum = int(
            await session.scalar(
                select(func.coalesce(func.sum(BillingLedgerEntry.amount_paise), 0)).where(
                    BillingLedgerEntry.order_id == order.id
                )
            )
            or 0
        )
        remote_amount = payment.get("amount")
        remote_refunded = payment.get("amount_refunded")
        try:
            remote_amount_paise = int(remote_amount)
            remote_refunded_paise = int(remote_refunded or 0)
        except (TypeError, ValueError):
            remote_amount_paise = None
            remote_refunded_paise = None

        expected_net: int | None = None
        if remote_amount_paise is not None and remote_refunded_paise is not None:
            expected_net = remote_amount_paise - remote_refunded_paise
        drift = (
            expected_net is None
            or ledger_sum != expected_net
            or remote_amount_paise != order.total_paise
        )
        if drift:
            problems += 1
            BILLING_RECONCILE_MISMATCH.inc()
            logger.warning(
                "billing.ad_reconcile_drift",
                extra={
                    "extra_fields": {
                        "order_id": str(order.id),
                        "order_status": order.status,
                        "order_total_paise": order.total_paise,
                        "ledger_sum_paise": ledger_sum,
                        "razorpay_amount_paise": remote_amount_paise,
                        "razorpay_amount_refunded_paise": remote_refunded_paise,
                        "expected_net_paise": expected_net,
                    }
                },
            )

    # Task 10's amount_mismatch forensics path: a `failed` order can still
    # carry a razorpay_payment_id. Normally that payment was never captured
    # (that's WHY it failed) so zero ledger rows is correct - but if
    # Razorpay's own record says the payment WAS captured, money moved and
    # nothing was ever ledgered. Reported distinctly (not `_drift`) so ops
    # can act on it as "go issue a refund", not "investigate a bookkeeping
    # bug".
    dead_orders = (
        await session.scalars(
            select(AdOrder).where(
                AdOrder.status == "failed",
                AdOrder.updated_at >= since,
                AdOrder.razorpay_payment_id.is_not(None),
            )
        )
    ).all()
    for order in dead_orders:
        assert order.razorpay_payment_id is not None  # narrowed by the query
        try:
            payment = await client.fetch_payment(order.razorpay_payment_id)
        except RazorpayError as exc:
            problems += 1
            logger.warning(
                "billing.ad_reconcile_fetch_failed",
                extra={"extra_fields": {"order_id": str(order.id), "exc_type": type(exc).__name__}},
            )
            continue
        if str(payment.get("status")) == "captured":
            problems += 1
            BILLING_RECONCILE_MISMATCH.inc()
            logger.warning(
                "billing.ad_reconcile_captured_unledgered",
                extra={
                    "extra_fields": {
                        "order_id": str(order.id),
                        "razorpay_payment_id": order.razorpay_payment_id,
                        "razorpay_amount_paise": payment.get("amount"),
                    }
                },
            )

    # Orphan check: a ledger row must always trace back to a live order row.
    # order_id is nullable in the schema (defensive - never written NULL by
    # either applier) and FK-constrained where set, so the "points at a
    # missing order" half of this is unreachable through the app today; the
    # outer join still covers it rather than assuming the FK forever holds.
    orphan_rows = (
        await session.execute(
            select(BillingLedgerEntry.id, BillingLedgerEntry.order_id)
            .outerjoin(AdOrder, AdOrder.id == BillingLedgerEntry.order_id)
            .where(BillingLedgerEntry.created_at >= since, AdOrder.id.is_(None))
        )
    ).all()
    for entry_id, order_id in orphan_rows:
        problems += 1
        BILLING_RECONCILE_MISMATCH.inc()
        logger.warning(
            "billing.ad_reconcile_drift",
            extra={
                "extra_fields": {
                    "order_id": str(order_id) if order_id else None,
                    "ledger_entry_id": str(entry_id),
                    "reason": "orphan_ledger_entry",
                }
            },
        )

    return problems
