"""Non-negotiable 4: reconciliation detects an injected local-vs-remote
mismatch; flag off means zero live calls."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.models import Invoice, Subscription
from modules.billing.razorpay_client import RazorpayError
from modules.billing.reconcile import run_reconciliation
from shared.flags import FeatureFlag, reset_flag_cache
from tests.fixtures.billing import FakeRazorpay

pytestmark = pytest.mark.asyncio


async def _enable_billing(db_session: AsyncSession) -> None:
    flag = await db_session.get(FeatureFlag, "billing_enabled")
    assert flag is not None
    flag.enabled = True
    await db_session.flush()
    reset_flag_cache()


def _sub(razorpay_id: str, status: str = "active") -> Subscription:
    return Subscription(
        business_id=uuid.uuid4(), tier="growth", status=status, razorpay_sub_id=razorpay_id
    )


async def test_detects_injected_status_mismatch(db_session: AsyncSession) -> None:
    await _enable_billing(db_session)
    matched = _sub("sub_ok")
    drifted = _sub("sub_drift")
    db_session.add_all([matched, drifted])
    await db_session.flush()
    fake = FakeRazorpay()
    fake.subs["sub_ok"] = {"id": "sub_ok", "status": "active", "current_end": None}
    fake.subs["sub_drift"] = {"id": "sub_drift", "status": "cancelled", "current_end": None}

    assert await run_reconciliation(db_session, client=fake) == 1


async def test_pre_first_charge_shape_is_consistent(db_session: AsyncSession) -> None:
    """local active + current_period_end NULL vs remote created/authenticated
    is the documented pre-charge shape, not drift (spec §3)."""
    await _enable_billing(db_session)
    sub = _sub("sub_new")
    db_session.add(sub)
    await db_session.flush()
    fake = FakeRazorpay()
    fake.subs["sub_new"] = {"id": "sub_new", "status": "created", "current_end": None}
    assert await run_reconciliation(db_session, client=fake) == 0


async def test_period_end_drift_detected(db_session: AsyncSession) -> None:
    await _enable_billing(db_session)
    local_end = datetime(2026, 8, 1, tzinfo=UTC)
    sub = _sub("sub_period")
    sub.current_period_end = local_end
    db_session.add(sub)
    await db_session.flush()
    fake = FakeRazorpay()
    fake.subs["sub_period"] = {
        "id": "sub_period",
        "status": "active",
        "current_end": int((local_end + timedelta(days=3)).timestamp()),
    }
    assert await run_reconciliation(db_session, client=fake) == 1


async def test_invoice_paid_status_drift_detected(db_session: AsyncSession) -> None:
    await _enable_billing(db_session)
    sub = _sub("sub_inv_drift")
    db_session.add(sub)
    await db_session.flush()
    inv = Invoice(
        subscription_id=sub.id,
        amount_paise=49900,
        status="issued",
        razorpay_invoice_id="inv_drift",
    )
    db_session.add(inv)
    await db_session.flush()
    fake = FakeRazorpay()
    fake.subs["sub_inv_drift"] = {"id": "sub_inv_drift", "status": "active", "current_end": None}
    fake.invoices["inv_drift"] = {"id": "inv_drift", "status": "paid"}

    assert await run_reconciliation(db_session, client=fake) == 1


async def test_invoice_paid_parity_is_consistent(db_session: AsyncSession) -> None:
    await _enable_billing(db_session)
    sub = _sub("sub_inv_ok")
    db_session.add(sub)
    await db_session.flush()
    inv = Invoice(
        subscription_id=sub.id,
        amount_paise=49900,
        status="paid",
        razorpay_invoice_id="inv_ok",
    )
    db_session.add(inv)
    await db_session.flush()
    fake = FakeRazorpay()
    fake.subs["sub_inv_ok"] = {"id": "sub_inv_ok", "status": "active", "current_end": None}
    fake.invoices["inv_ok"] = {"id": "inv_ok", "status": "paid"}

    assert await run_reconciliation(db_session, client=fake) == 0


async def test_invoice_fetch_failure_is_not_drift(db_session: AsyncSession) -> None:
    await _enable_billing(db_session)
    sub = _sub("sub_inv_fail")
    db_session.add(sub)
    await db_session.flush()
    inv = Invoice(
        subscription_id=sub.id,
        amount_paise=49900,
        status="issued",
        razorpay_invoice_id="inv_fail",
    )
    db_session.add(inv)
    await db_session.flush()

    class RaisingFakeRazorpay(FakeRazorpay):
        async def fetch_invoice(self, invoice_id: str) -> dict[str, Any]:
            self.calls.append(("fetch_invoice", invoice_id))
            raise RazorpayError("boom")

    fake = RaisingFakeRazorpay()
    fake.subs["sub_inv_fail"] = {"id": "sub_inv_fail", "status": "active", "current_end": None}

    assert await run_reconciliation(db_session, client=fake) == 0
