"""Money-path webhook (non-negotiables 1+2): HMAC signature verified,
replay = one effect, flag off = 404 with zero side effects, stored payloads
are scrubbed."""

import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.billing.models import PaymentEvent, Subscription
from modules.directory.models import Business
from settings import get_settings
from shared.db import get_session
from shared.flags import FeatureFlag, reset_flag_cache

pytestmark = pytest.mark.asyncio

SECRET = "whsec_test"


@pytest.fixture
async def api(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    app = create_app()

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


async def _seed_sub(session: AsyncSession) -> Subscription:
    business = Business(
        name="Kovai Mills",
        slug=f"kovai-{uuid.uuid4().hex[:8]}",
        owner_user_id=uuid.uuid4(),
        type="farm",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    sub = Subscription(business_id=business.id, tier="growth", razorpay_sub_id="sub_000001")
    session.add(sub)
    await session.flush()
    return sub


def _signed(body: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(body).encode()
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {
        "x-razorpay-signature": signature,
        "x-razorpay-event-id": body.get("_event_id", "evt_1"),
        "content-type": "application/json",
    }


def _charged_body(event_id: str = "evt_1") -> dict[str, Any]:
    period_end = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    return {
        "_event_id": event_id,
        "event": "subscription.charged",
        "payload": {
            "subscription": {"entity": {"id": "sub_000001", "current_end": period_end}},
            "payment": {
                "entity": {
                    "id": "pay_1",
                    "amount": 49900,
                    "invoice_id": "inv_1",
                    "card": {"last4": "1111"},
                    "email": "payer@example.com",
                }
            },
        },
    }


async def test_flag_off_webhook_is_404_with_no_side_effects(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    raw, headers = _signed(_charged_body())
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 404
    assert await session.scalar(select(func.count(PaymentEvent.id))) == 0


async def test_bad_signature_rejected_no_row(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    await _enable_billing(session)
    await _seed_sub(session)
    raw, headers = _signed(_charged_body())
    headers["x-razorpay-signature"] = "deadbeef"
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 400
    assert await session.scalar(select(func.count(PaymentEvent.id))) == 0


async def test_charged_processes_and_replay_is_one_effect(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    sub = await _seed_sub(session)
    raw, headers = _signed(_charged_body())

    first = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert first.status_code == 200 and first.json()["status"] == "ok"
    await session.refresh(sub)
    assert sub.status == "active" and sub.current_period_end is not None
    first_period_end = sub.current_period_end

    replay = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert replay.status_code == 200 and replay.json()["status"] == "duplicate"
    assert await session.scalar(select(func.count(PaymentEvent.id))) == 1
    await session.refresh(sub)
    assert sub.current_period_end == first_period_end  # one effect, not two


async def test_stored_payload_is_scrubbed(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    await _enable_billing(session)
    await _seed_sub(session)
    raw, headers = _signed(_charged_body("evt_scrub"))
    await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    event = await session.scalar(
        select(PaymentEvent).where(PaymentEvent.provider_event_id == "evt_scrub")
    )
    assert event is not None and event.outcome == "processed"
    dumped = json.dumps(event.payload)
    assert "card" not in dumped and "payer@example.com" not in dumped


async def test_unknown_subscription_records_unmatched_200(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    body = _charged_body("evt_unmatched")
    body["payload"]["subscription"]["entity"]["id"] = "sub_ghost"
    body["payload"]["payment"]["entity"].pop("invoice_id")
    raw, headers = _signed(body)
    response = await client.post("/billing/webhook/razorpay", content=raw, headers=headers)
    assert response.status_code == 200
    event = await session.scalar(
        select(PaymentEvent).where(PaymentEvent.provider_event_id == "evt_unmatched")
    )
    assert event is not None and event.outcome == "unmatched"
