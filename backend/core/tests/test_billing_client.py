"""Razorpay client: flag-gated live calls (defense in depth under the route
404s) and payload scrubbing ("never store card data" applies to the raw
webhook log)."""

import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from modules.billing.razorpay_client import BillingDisabledError, RazorpayClient, RazorpayError
from modules.billing.sanitize import scrub_payload
from settings import get_settings
from shared import flags

pytestmark = pytest.mark.asyncio


def _enable_billing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seed the in-process flag cache: flag_enabled() consults _cache before
    any DB read, and monkeypatch teardown restores it even on a crash."""
    monkeypatch.setitem(flags._cache, "billing_enabled", (time.monotonic(), True))


async def test_flag_off_blocks_every_live_call(monkeypatch: pytest.MonkeyPatch) -> None:
    # seed False so the check never needs a DB - keeps this a pure unit test
    # (the fail-closed unknown-flag default is covered in test_flags.py)
    monkeypatch.setitem(flags._cache, "billing_enabled", (time.monotonic(), False))
    client = RazorpayClient("key", "secret")
    with pytest.raises(BillingDisabledError):
        await client.fetch_subscription("sub_1")
    with pytest.raises(BillingDisabledError):
        await client.create_subscription(plan_id="plan_1")


async def test_missing_credentials_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_billing(monkeypatch)
    client = RazorpayClient("", "")
    with pytest.raises(RazorpayError, match="not configured"):
        await client.fetch_subscription("sub_1")


async def test_request_and_error_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization", "")
        if request.url.path.endswith("/missing"):
            return httpx.Response(404, json={"error": {"description": "not found"}})
        return httpx.Response(200, json={"id": "sub_1", "status": "active"})

    transport = httpx.MockTransport(handler)
    client = RazorpayClient("key_id", "key_secret", transport=transport)
    _enable_billing(monkeypatch)
    body = await client.fetch_subscription("sub_1")
    assert body["status"] == "active"
    assert seen["path"] == "/v1/subscriptions/sub_1"
    assert seen["auth"].startswith("Basic ")
    with pytest.raises(RazorpayError):
        await client.fetch_subscription("missing")


async def test_non_json_2xx_raises_razorpay_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    transport = httpx.MockTransport(handler)
    client = RazorpayClient("key_id", "key_secret", transport=transport)
    _enable_billing(monkeypatch)
    with pytest.raises(RazorpayError, match="invalid json"):
        await client.fetch_subscription("sub_1")


async def test_stub_is_inert_when_app_env_is_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """money-path review item 3: razorpay_test_stub is a hard AND against
    app_env != "prod" (D09 otp_test_peek / main.py:229 precedent) - a
    misconfigured prod deploy with the stub flag left on must still attempt
    a REAL Razorpay call, never return canned data. No credentials are
    configured here, so the real path fails with "not configured" rather
    than returning the stub's canned response - that failure IS the proof
    the stub was not used."""
    monkeypatch.setenv("RAZORPAY_TEST_STUB", "true")
    monkeypatch.setenv("APP_ENV", "prod")
    get_settings.cache_clear()
    _enable_billing(monkeypatch)
    client = RazorpayClient("", "")
    now = datetime.now(UTC)
    expire_by = int((now + timedelta(hours=24)).timestamp())
    with pytest.raises(RazorpayError, match="not configured"):
        await client.create_payment_link(
            amount_paise=100,
            description="test",
            reference_id="order-1",
            callback_url="https://example.com/callback",
            expire_by=expire_by,
        )
    with pytest.raises(RazorpayError, match="not configured"):
        await client.fetch_payment("pay_1")
    with pytest.raises(RazorpayError, match="not configured"):
        await client.fetch_payment_link("plink_1")


async def test_stub_is_active_outside_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flip side of the guard above: with the SAME stub flag and no
    credentials, a non-prod app_env DOES get the canned response - proving
    the guard is app_env-specific, not a blanket "stub never works"."""
    monkeypatch.setenv("RAZORPAY_TEST_STUB", "true")
    monkeypatch.setenv("APP_ENV", "dev")
    get_settings.cache_clear()
    _enable_billing(monkeypatch)
    client = RazorpayClient("", "")
    now = datetime.now(UTC)
    expire_by = int((now + timedelta(hours=24)).timestamp())
    result = await client.create_payment_link(
        amount_paise=100,
        description="test",
        reference_id="order-1",
        callback_url="https://example.com/callback",
        expire_by=expire_by,
    )
    assert result["id"] == "plink_test_order1"
    assert result["short_url"] == "https://example.com/callback"


def test_scrub_payload_strips_instrument_and_contact_fields() -> None:
    payload = {
        "event": "subscription.charged",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_1",
                    "amount": 49900,
                    "card": {"last4": "1111", "network": "Visa"},
                    "card_id": "card_1",
                    "vpa": "user@upi",
                    "contact": "+911234567890",
                    "email": "payer@example.com",
                    "notes": [{"token": "tok_1"}],
                }
            }
        },
    }
    scrubbed = scrub_payload(payload)
    entity = scrubbed["payload"]["payment"]["entity"]
    assert entity == {"id": "pay_1", "amount": 49900, "notes": [{}]}
