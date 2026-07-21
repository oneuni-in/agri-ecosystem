"""Dunning state machine (non-negotiable 3): failed -> past_due -> reminders
on due ticks -> canceled on exhaustion+grace; charged-during-past_due
recovers to active. Clock injected everywhere - no sleeps."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.models import Invoice, Subscription
from modules.billing.razorpay_client import RazorpayError
from modules.billing.service import (
    apply_charge_failed,
    apply_subscription_charged,
    dunning_offsets,
    process_webhook_event,
    run_due_dunning,
)
from modules.directory.lookups import business_ref
from modules.directory.models import Business
from settings import get_settings
from shared.flags import FeatureFlag, reset_flag_cache
from shared.lookups import register_business_resolver
from tests.fixtures.billing import FakeRazorpay

pytestmark = pytest.mark.asyncio

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


async def _enable_billing(db_session: AsyncSession) -> None:
    flag = await db_session.get(FeatureFlag, "billing_enabled")
    assert flag is not None
    flag.enabled = True
    await db_session.flush()
    reset_flag_cache()


async def _make_sub(db_session: AsyncSession, *, razorpay_id: str = "sub_000001") -> Subscription:
    owner = uuid.uuid4()
    business = Business(
        name="Kovai Mills",
        slug=f"kovai-{uuid.uuid4().hex[:8]}",
        owner_user_id=owner,
        type="farm",
        primary_pincode="641001",
    )
    db_session.add(business)
    await db_session.flush()
    register_business_resolver(business_ref)
    sub = Subscription(business_id=business.id, tier="growth", razorpay_sub_id=razorpay_id)
    db_session.add(sub)
    await db_session.flush()
    return sub


def test_dunning_offsets_parse_and_validate() -> None:
    assert dunning_offsets(get_settings()) == [
        timedelta(hours=24),
        timedelta(hours=72),
        timedelta(hours=168),
    ]


async def test_charge_failure_enters_dunning(db_session: AsyncSession) -> None:
    sub = await _make_sub(db_session)
    pending = await apply_charge_failed(db_session, sub, now=T0, settings=get_settings())
    assert sub.status == "past_due"
    assert sub.past_due_since == T0
    assert sub.dunning_attempt == 0
    assert sub.next_retry_at == T0 + timedelta(hours=24)
    assert [event_type for event_type, _ in pending] == ["billing.payment_failed"]
    payload = pending[0][1]
    assert payload["vars"]["business_name"] == "Kovai Mills"
    # second failure event while already past_due: no double transition
    assert await apply_charge_failed(db_session, sub, now=T0, settings=get_settings()) == []


async def test_full_dunning_walk_to_cancellation(db_session: AsyncSession) -> None:
    await _enable_billing(db_session)
    sub = await _make_sub(db_session)
    fake = FakeRazorpay()
    fake.subs["sub_000001"] = {"id": "sub_000001", "status": "halted", "current_end": None}
    settings = get_settings()
    await apply_charge_failed(db_session, sub, now=T0, settings=settings)

    # tick before due: nothing happens
    processed, pending = await run_due_dunning(
        db_session, now=T0 + timedelta(hours=1), client=fake, settings=settings
    )
    assert processed == 0

    # reminders at each cumulative offset (24h, 72h, 168h)
    reminders = 0
    for offset_hours in (24, 72, 168):
        processed, pending = await run_due_dunning(
            db_session,
            now=T0 + timedelta(hours=offset_hours, minutes=1),
            client=fake,
            settings=settings,
        )
        assert processed == 1
        reminders += sum(1 for event_type, _ in pending if event_type == "billing.dunning_reminder")
        assert sub.status == "past_due"
    assert reminders == 3
    assert sub.dunning_attempt == 3
    assert sub.next_retry_at == T0 + timedelta(hours=168) + timedelta(
        days=settings.dunning_grace_days
    )

    # grace elapsed -> cancel at provider + locally
    processed, pending = await run_due_dunning(
        db_session,
        now=T0 + timedelta(hours=168) + timedelta(days=settings.dunning_grace_days, minutes=1),
        client=fake,
        settings=settings,
    )
    assert processed == 1
    assert sub.status == "canceled"
    assert ("cancel", "sub_000001") in fake.calls
    assert [event_type for event_type, _ in pending] == ["billing.subscription_canceled"]


async def test_dunning_cancel_provider_error_isolated_per_sub(db_session: AsyncSession) -> None:
    """A provider error canceling one due sub must not abort the tick for the
    rest of the batch: the failing sub stays past_due for retry next tick,
    other due subs still advance normally."""
    await _enable_billing(db_session)
    settings = get_settings()
    sub_a = await _make_sub(db_session, razorpay_id="sub_a")
    sub_b = await _make_sub(db_session, razorpay_id="sub_b")

    class FlakyCancelRazorpay(FakeRazorpay):
        async def cancel_subscription(self, sub_id: str) -> dict[str, Any]:
            if sub_id == "sub_a":
                self.calls.append(("cancel", sub_id))
                raise RazorpayError("boom")
            return await super().cancel_subscription(sub_id)

    fake = FlakyCancelRazorpay()
    fake.subs["sub_a"] = {"id": "sub_a", "status": "halted", "current_end": None}
    fake.subs["sub_b"] = {"id": "sub_b", "status": "halted", "current_end": None}

    await apply_charge_failed(db_session, sub_a, now=T0, settings=settings)
    await apply_charge_failed(db_session, sub_b, now=T0, settings=settings)

    # sub_a: exhaustion + grace already elapsed -> cancellation is due now.
    sub_a.dunning_attempt = len(dunning_offsets(settings))
    sub_a.next_retry_at = T0
    await db_session.flush()
    # sub_b: left at its first reminder offset, due for a normal tick.

    processed, pending = await run_due_dunning(
        db_session, now=T0 + timedelta(hours=25), client=fake, settings=settings
    )

    assert processed == 2
    assert ("cancel", "sub_a") in fake.calls
    # sub_a: provider cancel failed - stays past_due, untouched retry time
    # means the (already-past) next_retry_at still picks it up next tick.
    assert sub_a.status == "past_due"
    assert sub_a.next_retry_at == T0
    # sub_b: unaffected by sub_a's failure - advances normally.
    assert sub_b.status == "past_due"
    assert sub_b.dunning_attempt == 1
    assert [event_type for event_type, _ in pending] == ["billing.dunning_reminder"]


async def test_remote_recovery_during_dunning_tick(db_session: AsyncSession) -> None:
    """Razorpay auto-retried and charged, but we missed the webhook: the tick
    syncs remote state and recovers instead of reminding."""
    await _enable_billing(db_session)
    sub = await _make_sub(db_session)
    settings = get_settings()
    await apply_charge_failed(db_session, sub, now=T0, settings=settings)
    period_end = int((T0 + timedelta(days=30)).timestamp())
    fake = FakeRazorpay()
    fake.subs["sub_000001"] = {"id": "sub_000001", "status": "active", "current_end": period_end}

    _, pending = await run_due_dunning(
        db_session, now=T0 + timedelta(hours=25), client=fake, settings=settings
    )
    assert sub.status == "active"
    assert sub.dunning_attempt == 0 and sub.next_retry_at is None and sub.past_due_since is None
    assert [event_type for event_type, _ in pending] == ["billing.subscription_activated"]


async def test_charged_webhook_recovers_and_syncs_invoice(db_session: AsyncSession) -> None:
    sub = await _make_sub(db_session)
    settings = get_settings()
    await apply_charge_failed(db_session, sub, now=T0, settings=settings)
    period_end = T0 + timedelta(days=30)
    pending = await apply_subscription_charged(
        db_session,
        sub,
        period_end=period_end,
        payment={"invoice_id": "inv_1", "amount": 49900},
        now=T0 + timedelta(hours=2),
    )
    assert sub.status == "active" and sub.current_period_end == period_end
    assert [event_type for event_type, _ in pending] == ["billing.subscription_activated"]
    from sqlalchemy import select

    invoice = await db_session.scalar(select(Invoice).where(Invoice.razorpay_invoice_id == "inv_1"))
    assert invoice is not None and invoice.status == "paid" and invoice.amount_paise == 49900


async def test_flag_off_dunning_is_a_noop(db_session: AsyncSession) -> None:
    sub = await _make_sub(db_session)
    settings = get_settings()
    await apply_charge_failed(db_session, sub, now=T0, settings=settings)
    fake = FakeRazorpay()
    processed, pending = await run_due_dunning(
        db_session, now=T0 + timedelta(days=30), client=fake, settings=settings
    )
    assert processed == 0 and pending == [] and fake.calls == []


async def test_process_webhook_event_routes_by_type(db_session: AsyncSession) -> None:
    sub = await _make_sub(db_session)
    charged = {
        "event": "subscription.charged",
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_000001",
                    "current_end": int((T0 + timedelta(days=30)).timestamp()),
                }
            },
            "payment": {"entity": {"id": "pay_1", "amount": 49900, "invoice_id": "inv_9"}},
        },
    }
    outcome, pending = await process_webhook_event(
        db_session,
        event_type="subscription.charged",
        payload=charged,
        now=T0,
        settings=get_settings(),
    )
    assert outcome == "processed"
    assert sub.status == "active" and sub.current_period_end is not None

    outcome, _ = await process_webhook_event(
        db_session,
        event_type="payment.captured",
        payload={"event": "payment.captured"},
        now=T0,
        settings=get_settings(),
    )
    assert outcome == "ignored"

    unknown = {
        "event": "subscription.charged",
        "payload": {"subscription": {"entity": {"id": "sub_missing"}}},
    }
    outcome, _ = await process_webhook_event(
        db_session,
        event_type="subscription.charged",
        payload=unknown,
        now=T0,
        settings=get_settings(),
    )
    assert outcome == "unmatched"
