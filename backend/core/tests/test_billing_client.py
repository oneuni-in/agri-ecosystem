"""Razorpay client: flag-gated live calls (defense in depth under the route
404s) and payload scrubbing ("never store card data" applies to the raw
webhook log)."""

import time

import httpx
import pytest

from modules.billing.razorpay_client import BillingDisabledError, RazorpayClient, RazorpayError
from modules.billing.sanitize import scrub_payload
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
