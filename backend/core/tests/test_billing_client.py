"""Razorpay client: flag-gated live calls (defense in depth under the route
404s) and payload scrubbing ("never store card data" applies to the raw
webhook log)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from modules.billing.razorpay_client import BillingDisabledError, RazorpayClient, RazorpayError
from modules.billing.sanitize import scrub_payload
from settings import get_settings
from shared.db import reset_engine
from shared.flags import FeatureFlag, reset_flag_cache

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def _enable_billing(
    db_session: AsyncSession, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[None]:
    """Flip billing_enabled on for the duration of one test.

    RazorpayClient re-checks the flag via shared.flags.flag_enabled with no
    session argument - matching production, where the client has no
    request-scoped session at construction time. That call opens its OWN
    connection through shared.db.get_engine(), which (a) defaults to the dev
    DB, not the migrated test DB, and (b) even pointed at the test DB could
    never see db_session's write: conftest.py's db_session lives inside an
    outer transaction that only ever rolls back (per-test isolation), so
    db_session.commit() is invisible to any other connection. Point
    DATABASE_URL at the test DB and commit for real instead, mirroring
    test_otp_throttle.py's _audit_system pattern - then restore the flag
    afterwards so it doesn't leak into later tests sharing the
    session-scoped test DB.
    """
    flag = await db_session.get(FeatureFlag, "billing_enabled")
    assert flag is not None  # seeded in D03

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    reset_engine()
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text("UPDATE feature_flags SET enabled = true WHERE key = 'billing_enabled'")
            )
            await conn.commit()
        reset_flag_cache()
        yield
    finally:
        async with engine.connect() as conn:
            await conn.execute(
                text("UPDATE feature_flags SET enabled = false WHERE key = 'billing_enabled'")
            )
            await conn.commit()
        await engine.dispose()
        reset_flag_cache()


async def test_flag_off_blocks_every_live_call(db_session: AsyncSession) -> None:
    client = RazorpayClient("key", "secret")
    with pytest.raises(BillingDisabledError):
        await client.fetch_subscription("sub_1")
    with pytest.raises(BillingDisabledError):
        await client.create_subscription(plan_id="plan_1")


async def test_missing_credentials_raise(
    db_session: AsyncSession, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _enable_billing(db_session, database_url, monkeypatch):
        client = RazorpayClient("", "")
        with pytest.raises(RazorpayError, match="not configured"):
            await client.fetch_subscription("sub_1")


async def test_request_and_error_mapping(
    db_session: AsyncSession, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization", "")
        if request.url.path.endswith("/missing"):
            return httpx.Response(404, json={"error": {"description": "not found"}})
        return httpx.Response(200, json={"id": "sub_1", "status": "active"})

    transport = httpx.MockTransport(handler)
    client = RazorpayClient("key_id", "key_secret", transport=transport)
    async with _enable_billing(db_session, database_url, monkeypatch):
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
