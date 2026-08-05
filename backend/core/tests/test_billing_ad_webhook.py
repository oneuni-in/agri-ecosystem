"""M5 Task 10 - the webhook that turns Razorpay payments into ledger entries
and campaign activations (NN2: forged/replayed webhook rejected). Copies the
`_signed` HMAC pattern and `api` fixture verbatim from test_billing_webhook.py
(same verified/deduped webhook route, same billing_enabled gate) - only the
event bodies and assertions are new."""

import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.ads.models import Campaign, Creative
from modules.billing.ad_orders import create_ad_order, invoice_number_for
from modules.billing.models import AdOrder, BillingLedgerEntry, Invoice, PaymentEvent
from modules.directory.models import Business
from settings import get_settings
from shared.db import get_session
from shared.flags import FeatureFlag, reset_flag_cache
from tests.fixtures.billing import FakeRazorpay

pytestmark = pytest.mark.asyncio

SECRET = "whsec_test"

TODAY = date(2026, 8, 5)
FLIGHT_START = TODAY - timedelta(days=1)
FLIGHT_END = TODAY + timedelta(days=14)


@pytest.fixture
async def api(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    app = create_app()  # wires ads<->billing seams for real (main.create_app)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session


async def _enable_billing(session: AsyncSession) -> None:
    flag = await session.get(FeatureFlag, "billing_enabled")
    assert flag is not None
    flag.enabled = True
    await session.flush()
    reset_flag_cache()


def _signed(body: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(body).encode()
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {
        "x-razorpay-signature": signature,
        "x-razorpay-event-id": body.get("_event_id", "evt_1"),
        "content-type": "application/json",
    }


def _paid_body(
    plink_id: str, payment_id: str, amount: int, event_id: str = "evt_paid_1"
) -> dict[str, Any]:
    return {
        "_event_id": event_id,
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {"entity": {"id": plink_id, "reference_id": "ref-1"}},
            "payment": {"entity": {"id": payment_id, "amount": amount}},
        },
    }


def _expired_body(plink_id: str, event_id: str = "evt_expired_1") -> dict[str, Any]:
    return {
        "_event_id": event_id,
        "event": "payment_link.expired",
        "payload": {"payment_link": {"entity": {"id": plink_id, "reference_id": "ref-1"}}},
    }


def _refund_body(
    payment_id: str, refund_id: str, amount: int, event_id: str = "evt_refund_1"
) -> dict[str, Any]:
    return {
        "_event_id": event_id,
        "event": "refund.processed",
        "payload": {
            "payment": {"entity": {"id": payment_id, "amount": amount}},
            "refund": {"entity": {"id": refund_id, "payment_id": payment_id, "amount": amount}},
        },
    }


async def _seed_business(session: AsyncSession, owner: uuid.UUID | None = None) -> Business:
    business = Business(
        name="Kovai Mills",
        slug=f"kovai-{uuid.uuid4().hex[:8]}",
        owner_user_id=owner or uuid.uuid4(),
        type="farm",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    return business


def _campaign(business_id: uuid.UUID, **overrides: Any) -> Campaign:
    fields: dict[str, Any] = {
        "advertiser_business_id": business_id,
        "name": "Kharif push",
        "status": "pending_payment",
        "flight_start": FLIGHT_START,
        "flight_end": FLIGHT_END,
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
    return Campaign(**fields)


async def _seed_campaign(
    session: AsyncSession, business_id: uuid.UUID, **overrides: Any
) -> Campaign:
    campaign = _campaign(business_id, **overrides)
    session.add(campaign)
    await session.flush()
    return campaign


async def _approved_creative(session: AsyncSession, campaign: Campaign) -> Creative:
    creative = Creative(
        campaign_id=campaign.id,
        media_keys=["ads/x.jpg"],
        copy={"en": {"title": "t", "body": "b"}},
        target_url="https://example.com",
    )
    session.add(creative)
    await session.flush()
    creative.moderation_status = "approved"
    await session.flush()
    return creative


async def _seed_order(
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


# ---------------------------------------------------------------------------
# invoice_number_for - pure function (FY boundary)


def test_invoice_number_fy_boundary() -> None:
    assert invoice_number_for(7, date(2027, 3, 31)) == "MILK-26-27-000007"
    assert invoice_number_for(7, date(2027, 4, 1)) == "MILK-27-28-000007"


def test_invoice_number_pads_seq() -> None:
    assert invoice_number_for(1, date(2026, 8, 5)) == "MILK-26-27-000001"


# ---------------------------------------------------------------------------
# payment_link.paid -> ledger + invoice + campaign activation


async def test_paid_webhook_end_to_end(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    """Order paid, exactly one ledger row, a numbered invoice, and - because
    the campaign already has an approved creative waiting - the ads<->billing
    seam carries the payment all the way to `active` (both activation gates
    clear inside billing's own webhook transaction)."""
    client, session = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    await _approved_creative(session, campaign)
    order = await _seed_order(session, campaign, business.id, plink_id="plink_paid_1")

    raw, headers = _signed(_paid_body("plink_paid_1", "pay_paid_1", 118_000))
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "ok"

    await session.refresh(order)
    assert order.status == "paid"
    assert order.razorpay_payment_id == "pay_paid_1"

    ledger_rows = (
        await session.scalars(
            select(BillingLedgerEntry).where(BillingLedgerEntry.order_id == order.id)
        )
    ).all()
    assert len(ledger_rows) == 1
    assert ledger_rows[0].entry_type == "ad_charge"
    assert ledger_rows[0].amount_paise == 118_000
    assert ledger_rows[0].business_id == business.id
    assert ledger_rows[0].campaign_id == campaign.id

    invoice = await session.scalar(select(Invoice).where(Invoice.order_id == order.id))
    assert invoice is not None
    assert invoice.status == "paid"
    assert invoice.subscription_id is None
    assert invoice.amount_paise == 118_000
    assert invoice.taxable_paise == 100_000
    assert invoice.gst_paise == 18_000
    assert invoice.invoice_number == "MILK-26-27-000001"

    await session.refresh(campaign)
    assert campaign.status == "active"  # payment + pre-approved creative both cleared
    assert campaign.paid_at is not None


async def test_forged_signature_rejected(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    """NN2a: a tampered signature must 400 with zero orders/ledger rows touched."""
    client, session = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    order = await _seed_order(session, campaign, business.id, plink_id="plink_forged_1")

    raw, headers = _signed(_paid_body("plink_forged_1", "pay_forged_1", 118_000))
    headers["x-razorpay-signature"] = "deadbeef"
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 400

    assert await session.scalar(select(func.count(PaymentEvent.id))) == 0
    await session.refresh(order)
    assert order.status == "created"
    assert await session.scalar(select(func.count(BillingLedgerEntry.id))) == 0


async def test_replayed_body_is_duplicate(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    """NN2b: identical signed bytes replayed -> second delivery is a
    duplicate, ledger count stays 1."""
    client, session = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    order = await _seed_order(session, campaign, business.id, plink_id="plink_replay_1")

    raw, headers = _signed(_paid_body("plink_replay_1", "pay_replay_1", 118_000))
    first = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert first.status_code == 200 and first.json()["status"] == "ok"

    replay = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert replay.status_code == 200 and replay.json()["status"] == "duplicate"

    assert await session.scalar(select(func.count(BillingLedgerEntry.id))) == 1
    await session.refresh(order)
    assert order.status == "paid"


async def test_rewrapped_retry_is_ignored(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    """NN2c: the SAME plink/payment redelivered inside a DIFFERENT signed
    body (fresh `_event_id`) passes the body-hash dedupe as a brand-new
    event - order-level idempotency (order already `paid`) must still stop
    it from appending a second ledger row."""
    client, session = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    order = await _seed_order(session, campaign, business.id, plink_id="plink_rewrap_1")

    raw1, headers1 = _signed(
        _paid_body("plink_rewrap_1", "pay_rewrap_1", 118_000, event_id="evt_rewrap_1")
    )
    first = await client.post("/billing/webhook/razorpay", content=raw1, headers=headers1)
    assert first.status_code == 200 and first.json()["status"] == "ok"

    raw2, headers2 = _signed(
        _paid_body("plink_rewrap_1", "pay_rewrap_1", 118_000, event_id="evt_rewrap_2")
    )
    assert raw1 != raw2  # different body -> different dedupe hash, not caught by NN2b
    second = await client.post("/billing/webhook/razorpay", content=raw2, headers=headers2)
    assert second.status_code == 200 and second.json()["status"] == "ok"

    assert await session.scalar(select(func.count(PaymentEvent.id))) == 2
    second_event = await session.scalar(
        select(PaymentEvent).where(
            PaymentEvent.provider_event_id == hashlib.sha256(raw2).hexdigest()
        )
    )
    assert second_event is not None and second_event.outcome == "ignored"
    assert await session.scalar(select(func.count(BillingLedgerEntry.id))) == 1
    await session.refresh(order)
    assert order.status == "paid"


async def test_amount_mismatch_no_ledger_no_activation(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    await _approved_creative(session, campaign)
    order = await _seed_order(session, campaign, business.id, plink_id="plink_mismatch_1")

    raw, headers = _signed(_paid_body("plink_mismatch_1", "pay_mismatch_1", 117_999))
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "ok"

    await session.refresh(order)
    assert order.status == "failed"
    assert order.razorpay_payment_id is None
    assert await session.scalar(select(func.count(BillingLedgerEntry.id))) == 0
    assert await session.scalar(select(func.count(Invoice.id))) == 0

    await session.refresh(campaign)
    assert campaign.status == "pending_payment"  # untouched - no hook fired
    assert campaign.paid_at is None

    event = await session.scalar(
        select(PaymentEvent).where(
            PaymentEvent.provider_event_id == hashlib.sha256(raw).hexdigest()
        )
    )
    assert event is not None and event.outcome == "amount_mismatch"


# ---------------------------------------------------------------------------
# refund.processed -> ledger ad_refund + campaign paused


async def test_refund_appends_negative_and_pauses(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    business = await _seed_business(session)
    # campaign already active (direct ORM setup - the paid webhook path is
    # exercised elsewhere; this test only needs the refund half of the seam)
    campaign = await _seed_campaign(
        session,
        business.id,
        status="active",
        paid_at=datetime.now(UTC),
        budget_serves_total=5000,
        budget_serves_used=1200,
    )
    order = await _seed_order(
        session,
        campaign,
        business.id,
        plink_id="plink_refund_1",
        status="paid",
        razorpay_payment_id="pay_refund_1",
    )

    raw, headers = _signed(_refund_body("pay_refund_1", "rfnd_1", 118_000))
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "ok"

    await session.refresh(order)
    assert order.status == "refunded"

    ledger_rows = (
        await session.scalars(
            select(BillingLedgerEntry).where(BillingLedgerEntry.order_id == order.id)
        )
    ).all()
    assert len(ledger_rows) == 1
    assert ledger_rows[0].entry_type == "ad_refund"
    assert ledger_rows[0].amount_paise == -118_000

    await session.refresh(campaign)
    assert campaign.status == "paused"
    # budget zeroed out (total pinned to used) - durably non-serving even if
    # the campaign were later resumed; paid_at deliberately untouched.
    assert campaign.budget_serves_total == campaign.budget_serves_used == 1200
    assert campaign.paid_at is not None


async def test_refund_amount_capped_at_order_total(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """A refund reported larger than what was ever charged must not drive
    the append-only ledger below -order.total_paise."""
    client, session = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(
        session, business.id, status="active", paid_at=datetime.now(UTC)
    )
    order = await _seed_order(
        session,
        campaign,
        business.id,
        plink_id="plink_refund_cap_1",
        status="paid",
        razorpay_payment_id="pay_refund_cap_1",
    )

    raw, headers = _signed(_refund_body("pay_refund_cap_1", "rfnd_cap_1", 999_999))
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 200

    ledger_row = await session.scalar(
        select(BillingLedgerEntry).where(BillingLedgerEntry.order_id == order.id)
    )
    assert ledger_row is not None
    assert ledger_row.amount_paise == -118_000  # capped at order.total_paise, never -999_999


async def test_refund_on_unpaid_order_is_ignored(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    order = await _seed_order(session, campaign, business.id, plink_id="plink_refund_unpaid_1")

    raw, headers = _signed(_refund_body("pay_never_charged", "rfnd_ghost", 118_000))
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 200

    await session.refresh(order)
    assert order.status == "created"  # untouched: no order matches that payment id
    assert await session.scalar(select(func.count(BillingLedgerEntry.id))) == 0


# ---------------------------------------------------------------------------
# payment_link.expired -> re-checkout allowed


async def test_expired_allows_recheckout(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    await _enable_billing(session)
    owner = uuid.uuid4()
    business = await _seed_business(session, owner=owner)
    campaign = await _seed_campaign(session, business.id)
    order = await _seed_order(session, campaign, business.id, plink_id="plink_expire_1")

    raw, headers = _signed(_expired_body("plink_expire_1"))
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "ok"

    await session.refresh(order)
    assert order.status == "expired"

    await session.refresh(campaign)
    assert campaign.status == "pending_payment"  # no hook fired - stays payable

    # the partial-unique index on ad_orders excludes 'expired' -> a fresh
    # checkout for the same campaign must succeed.
    new_order = await create_ad_order(
        session,
        user_id=owner,
        campaign_id=campaign.id,
        buyer_gstin=None,
        client=FakeRazorpay(),
        settings=get_settings(),
        now=datetime.now(UTC),
    )
    assert new_order.status == "created"
    assert new_order.id != order.id


async def test_paid_order_ignores_late_expiry(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    """Razorpay can race a payment against its own expiry notification - an
    already-paid order must not be resurrected into 'expired'."""
    client, session = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    order = await _seed_order(
        session,
        campaign,
        business.id,
        plink_id="plink_late_expire_1",
        status="paid",
        razorpay_payment_id="pay_late_expire_1",
    )

    raw, headers = _signed(_expired_body("plink_late_expire_1"))
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 200

    await session.refresh(order)
    assert order.status == "paid"


async def test_unmatched_plink_id_records_unmatched_200(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    raw, headers = _signed(_paid_body("plink_ghost", "pay_ghost", 1))
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 200
    event = await session.scalar(
        select(PaymentEvent).where(
            PaymentEvent.provider_event_id == hashlib.sha256(raw).hexdigest()
        )
    )
    assert event is not None and event.outcome == "unmatched"
