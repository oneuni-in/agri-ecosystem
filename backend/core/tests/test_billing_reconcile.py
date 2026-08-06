"""Non-negotiable 4: reconciliation detects an injected local-vs-remote
mismatch; flag off means zero live calls.

M5 Task 11 (NN3): the ad-order ledger reconciliation tests below extend the
same file/fixture conventions to `reconcile_ad_orders` - the ad-revenue
ledger (Task 9/10) must sum to EXACTLY what Razorpay captured/refunded.
Orders are driven through the REAL Task-10 webhook appliers (direct
in-session calls, not the HTTP route - cheaper, and the route's signature/
dedupe machinery is already covered by test_billing_ad_webhook.py)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign
from modules.billing.ad_orders import apply_payment_link_paid, apply_refund_processed
from modules.billing.models import AdOrder, BillingLedgerEntry, Invoice, Subscription
from modules.billing.razorpay_client import RazorpayError
from modules.billing.reconcile import reconcile_ad_orders, run_reconciliation
from modules.directory.models import Business
from settings import get_settings
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


# ---------------------------------------------------------------------------
# M5 Task 11 (NN3): reconcile_ad_orders - ad-revenue ledger vs Razorpay

TODAY = date(2026, 8, 5)
NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


async def _seed_business(session: AsyncSession) -> Business:
    business = Business(
        name="Kovai Mills",
        slug=f"kovai-{uuid.uuid4().hex[:8]}",
        owner_user_id=uuid.uuid4(),
        type="farm",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    return business


async def _seed_campaign(
    session: AsyncSession, business_id: uuid.UUID, **overrides: Any
) -> Campaign:
    fields: dict[str, Any] = {
        "advertiser_business_id": business_id,
        "name": "Kharif push",
        "status": "pending_payment",
        "flight_start": TODAY - timedelta(days=1),
        "flight_end": TODAY + timedelta(days=14),
        "price_paise": 118_000,
        "price_subtotal_paise": 100_000,
        "price_gst_paise": 18_000,
        "pricing_model": "cpm",
        "rate_card_version": 1,
        "budget_serves_total": 5000,
        "quote": {
            "campaign_name": "Kharif push",
            "subtotal_paise": 100_000,
            "gst_paise": 18_000,
            "total_paise": 118_000,
        },
    }
    fields.update(overrides)
    campaign = Campaign(**fields)
    session.add(campaign)
    await session.flush()
    return campaign


async def _seed_ad_order(
    session: AsyncSession,
    campaign: Campaign,
    business_id: uuid.UUID,
    *,
    plink_id: str,
    **overrides: Any,
) -> AdOrder:
    order = AdOrder(
        campaign_id=campaign.id,
        business_id=business_id,
        status="created",
        subtotal_paise=100_000,
        gst_paise=18_000,
        total_paise=118_000,
        quote=dict(campaign.quote or {}),
        razorpay_plink_id=plink_id,
    )
    for key, value in overrides.items():
        setattr(order, key, value)
    session.add(order)
    await session.flush()
    return order


async def _pay_order(session: AsyncSession, order: AdOrder, payment_id: str, amount: int) -> None:
    """Drives the order through the REAL Task-10 applier, in-session."""
    outcome, _ = await apply_payment_link_paid(
        session,
        payload={
            "payload": {
                "payment_link": {"entity": {"id": order.razorpay_plink_id}},
                "payment": {"entity": {"id": payment_id, "amount": amount}},
            }
        },
        now=NOW,
        settings=get_settings(),
    )
    assert outcome == "ok"
    await session.refresh(order)


async def _refund_order(session: AsyncSession, order: AdOrder, refund_id: str, amount: int) -> None:
    outcome, _ = await apply_refund_processed(
        session,
        payload={
            "payload": {
                "refund": {
                    "entity": {
                        "id": refund_id,
                        "payment_id": order.razorpay_payment_id,
                        "amount": amount,
                    }
                }
            }
        },
        now=NOW,
    )
    assert outcome == "ok"
    await session.refresh(order)


async def _refresh_all(session: AsyncSession, rows: list[AdOrder]) -> None:
    for row in rows:
        await session.refresh(row)


async def test_nn3_ad_ledger_matches_razorpay_exactly(db_session: AsyncSession) -> None:
    """3 paid orders + 1 partial refund + 1 full refund, driven through the
    real appliers; a FakeRazorpay mirroring what Razorpay would actually
    hold reconciles clean, and the ledger sum equals captured minus
    refunded EXACTLY (NN3)."""
    await _enable_billing(db_session)
    business = await _seed_business(db_session)
    fake = FakeRazorpay()

    campaign1 = await _seed_campaign(db_session, business.id)
    order1 = await _seed_ad_order(db_session, campaign1, business.id, plink_id="plink_nn3_1")
    await _pay_order(db_session, order1, "pay_nn3_1", 118_000)
    fake.payments["pay_nn3_1"] = {
        "id": "pay_nn3_1",
        "status": "captured",
        "amount": 118_000,
        "amount_refunded": 0,
    }

    campaign2 = await _seed_campaign(db_session, business.id)
    order2 = await _seed_ad_order(db_session, campaign2, business.id, plink_id="plink_nn3_2")
    await _pay_order(db_session, order2, "pay_nn3_2", 118_000)
    await _refund_order(db_session, order2, "rfnd_nn3_2", 40_000)  # partial - stays paid
    fake.payments["pay_nn3_2"] = {
        "id": "pay_nn3_2",
        "status": "captured",
        "amount": 118_000,
        "amount_refunded": 40_000,
    }

    campaign3 = await _seed_campaign(db_session, business.id)
    order3 = await _seed_ad_order(db_session, campaign3, business.id, plink_id="plink_nn3_3")
    await _pay_order(db_session, order3, "pay_nn3_3", 118_000)
    await _refund_order(db_session, order3, "rfnd_nn3_3", 118_000)  # full - flips refunded
    fake.payments["pay_nn3_3"] = {
        "id": "pay_nn3_3",
        "status": "refunded",
        "amount": 118_000,
        "amount_refunded": 118_000,
    }

    await _refresh_all(db_session, [order1, order2, order3])
    assert order2.status == "paid"
    assert order3.status == "refunded"

    since = NOW - timedelta(days=1)
    assert await reconcile_ad_orders(db_session, client=fake, since=since) == 0

    ledger_sum = await db_session.scalar(
        select(func.coalesce(func.sum(BillingLedgerEntry.amount_paise), 0))
    )
    captured = 118_000 * 3
    refunded = 40_000 + 118_000
    assert ledger_sum == captured - refunded  # NN3: exact, to the paise


async def test_ad_reconcile_amount_off_by_one_is_drift(db_session: AsyncSession) -> None:
    await _enable_billing(db_session)
    business = await _seed_business(db_session)
    campaign = await _seed_campaign(db_session, business.id)
    order = await _seed_ad_order(db_session, campaign, business.id, plink_id="plink_off_1")
    await _pay_order(db_session, order, "pay_off_1", 118_000)

    fake = FakeRazorpay()
    fake.payments["pay_off_1"] = {
        "id": "pay_off_1",
        "status": "captured",
        "amount": 118_001,
        "amount_refunded": 0,
    }
    since = NOW - timedelta(days=1)
    assert await reconcile_ad_orders(db_session, client=fake, since=since) == 1


async def test_ad_reconcile_detects_bogus_extra_ledger_row(db_session: AsyncSession) -> None:
    """Deletion is impossible (append-only, tested elsewhere) - the
    equivalent tamper here is an extra row nobody's applier produced,
    inserted via raw SQL the same way tests/test_billing_ledger_migration.py
    seeds fixtures. Sum-per-order drift catches it even though the row
    itself is individually well-formed."""
    await _enable_billing(db_session)
    business = await _seed_business(db_session)
    campaign = await _seed_campaign(db_session, business.id)
    order = await _seed_ad_order(db_session, campaign, business.id, plink_id="plink_bogus_1")
    await _pay_order(db_session, order, "pay_bogus_1", 118_000)

    await db_session.execute(
        text(
            "INSERT INTO billing.ledger_entries "
            "(id, entry_type, amount_paise, business_id, order_id, meta) "
            "VALUES (gen_random_uuid(), 'ad_refund', -1, :b, :o, CAST(:m AS jsonb))"
        ),
        {"b": business.id, "o": order.id, "m": '{"refund_id": "rfnd_bogus_1"}'},
    )
    await db_session.flush()

    fake = FakeRazorpay()
    fake.payments["pay_bogus_1"] = {
        "id": "pay_bogus_1",
        "status": "captured",
        "amount": 118_000,
        "amount_refunded": 0,
    }
    since = NOW - timedelta(days=1)
    assert await reconcile_ad_orders(db_session, client=fake, since=since) == 1


async def test_ad_reconcile_flags_captured_payment_on_failed_order(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Task 10's amount_mismatch path: a `failed` order still carries a
    razorpay_payment_id. If Razorpay's own record says that payment was
    actually captured, money moved with nothing ledgered - reportable and
    logged distinctly so ops knows to issue a refund, not chase a bug."""
    await _enable_billing(db_session)
    business = await _seed_business(db_session)
    campaign = await _seed_campaign(db_session, business.id)
    order = await _seed_ad_order(
        db_session,
        campaign,
        business.id,
        plink_id="plink_dead_1",
        status="failed",
        razorpay_payment_id="pay_dead_1",
    )
    fake = FakeRazorpay()
    fake.payments["pay_dead_1"] = {
        "id": "pay_dead_1",
        "status": "captured",
        "amount": order.total_paise,
        "amount_refunded": 0,
    }
    since = NOW - timedelta(days=1)
    with caplog.at_level("WARNING"):
        result = await reconcile_ad_orders(db_session, client=fake, since=since)
    assert result == 1
    assert "billing.ad_reconcile_captured_unledgered" in caplog.text


async def test_ad_reconcile_fetch_failure_counts_toward_nonzero_exit(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    await _enable_billing(db_session)
    business = await _seed_business(db_session)
    campaign = await _seed_campaign(db_session, business.id)
    order = await _seed_ad_order(db_session, campaign, business.id, plink_id="plink_fail_1")
    await _pay_order(db_session, order, "pay_fail_1", 118_000)

    class RaisingFakeRazorpay(FakeRazorpay):
        async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
            self.calls.append(("fetch_payment", payment_id))
            raise RazorpayError("boom")

    fake = RaisingFakeRazorpay()
    since = NOW - timedelta(days=1)
    with caplog.at_level("WARNING"):
        result = await reconcile_ad_orders(db_session, client=fake, since=since)
    assert result == 1  # fetch failures are NOT drift, but still nonzero
    assert "billing.ad_reconcile_fetch_failed" in caplog.text


async def test_ad_reconcile_flags_orphan_ledger_entry(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    await _enable_billing(db_session)
    business = await _seed_business(db_session)
    await db_session.execute(
        text(
            "INSERT INTO billing.ledger_entries "
            "(id, entry_type, amount_paise, business_id, order_id, meta) "
            "VALUES (gen_random_uuid(), 'ad_charge', 500, :b, NULL, '{}'::jsonb)"
        ),
        {"b": business.id},
    )
    await db_session.flush()

    fake = FakeRazorpay()
    since = NOW - timedelta(days=1)
    with caplog.at_level("WARNING"):
        result = await reconcile_ad_orders(db_session, client=fake, since=since)
    assert result == 1
    assert "billing.ad_reconcile_drift" in caplog.text
    assert fake.calls == []  # orphan check never touches Razorpay


async def test_ad_reconcile_since_window_filters_old_orders(db_session: AsyncSession) -> None:
    """An order genuinely predates the window - both its own `updated_at`
    AND its ledger row's `created_at` are before `since` - so it must stay
    out of scope. (Merely backdating `updated_at` on a fresh order does NOT
    exercise this: the ledger row itself still has a fresh `created_at` and
    the widened `ledger_touched_since` OR re-admits it - that re-entry
    behavior is the fix under test in
    test_ad_reconcile_reenters_scope_via_ledger_activity_after_partial_refund.
    Here the cutoff is placed strictly AFTER the order's real creation
    instant instead, which is the only way to genuinely exclude it.)"""
    await _enable_billing(db_session)
    business = await _seed_business(db_session)
    campaign = await _seed_campaign(db_session, business.id)
    order = await _seed_ad_order(db_session, campaign, business.id, plink_id="plink_old_1")
    await _pay_order(db_session, order, "pay_old_1", 118_000)

    fake = FakeRazorpay()
    # deliberately wrong - if the order were in scope this would be drift
    fake.payments["pay_old_1"] = {
        "id": "pay_old_1",
        "status": "captured",
        "amount": 1,
        "amount_refunded": 0,
    }
    since = datetime.now(UTC) + timedelta(minutes=1)
    assert await reconcile_ad_orders(db_session, client=fake, since=since) == 0
    assert fake.calls == []  # filtered out before any fetch_payment call


async def test_ad_reconcile_reenters_scope_via_ledger_activity_after_partial_refund(
    db_session: AsyncSession,
) -> None:
    """Fast-follow (reviewer Critical): apply_refund_processed's partial-
    refund path appends a ledger row but never mutates the AdOrder row
    itself (status stays `paid`, no column is written) - so `updated_at`
    never bumps. An order whose `updated_at` has already aged past the
    reconcile window, but which THEN receives a partial refund, must still
    re-enter scope on ledger activity alone - otherwise later drift on that
    order (e.g. a second, tampered refund) would be permanently unchecked.

    Backdating `updated_at` is a plain UPDATE on `billing.ad_orders` - that
    column carries no append-only trigger (only `ledger_entries` does) and
    app_rt already has UPDATE grant on ad_orders (the applier itself flips
    `order.status` this way) - so this runs on the ordinary `db_session`,
    not a separate admin connection. A separate connection couldn't see
    this row anyway: db_session's fixture never commits until the test's
    outer rollback, so a second connection would find nothing to update."""
    await _enable_billing(db_session)
    business = await _seed_business(db_session)
    campaign = await _seed_campaign(db_session, business.id)
    order = await _seed_ad_order(db_session, campaign, business.id, plink_id="plink_reentry_1")
    await _pay_order(db_session, order, "pay_reentry_1", 118_000)

    await db_session.execute(
        text("UPDATE billing.ad_orders SET updated_at = :old WHERE id = :id"),
        {"old": NOW - timedelta(days=30), "id": order.id},
    )
    await db_session.flush()

    # a partial refund lands AFTER the order aged out - per the bug report,
    # this does NOT touch the order row itself.
    await _refund_order(db_session, order, "rfnd_reentry_1", 40_000)
    await db_session.refresh(order)
    assert order.status == "paid"  # partial - unchanged
    assert order.updated_at < NOW - timedelta(days=3)  # still stale: confirms the hole exists

    fake = FakeRazorpay()
    fake.payments["pay_reentry_1"] = {
        "id": "pay_reentry_1",
        "status": "captured",
        "amount": 118_000,
        "amount_refunded": 40_000,
    }
    since = NOW - timedelta(days=3)
    assert await reconcile_ad_orders(db_session, client=fake, since=since) == 0
    assert ("fetch_payment", "pay_reentry_1") in fake.calls  # picked up despite stale updated_at

    # tamper: Razorpay's reported amount_refunded now disagrees with what
    # was actually refunded - must surface as drift, proving the order stays
    # reachable for future reconcile runs too, not just this one.
    fake.payments["pay_reentry_1"]["amount_refunded"] = 1_000
    assert await reconcile_ad_orders(db_session, client=fake, since=since) == 1
