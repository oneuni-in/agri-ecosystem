"""Push channel (D28): subscriptions CRUD + dispatch pipeline. Every send
lands in MockPushDriver's outbox - no network. notify.push_enabled seeds
false; tests that expect sends flip it on first (email-flag pattern)."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import cast

import httpx
import pytest
from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.session_service import WebPrincipal
from modules.notify.drivers import ExpiredSubscriptionError, MockPushDriver
from modules.notify.models import Delivery, Preference, PushSubscription
from modules.notify.service import NotifyRequest, dispatch
from shared.db import get_session
from shared.flags import FeatureFlag
from shared.security import register_principal_resolver

NOW = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
USER_A = uuid.uuid4()
USER_B = uuid.uuid4()

ENDPOINT_1 = "https://fcm.googleapis.com/fcm/send/aaaaaaaa"
ENDPOINT_2 = "https://web.push.apple.com/sub/bbbbbbbb"


def _resolver_for(
    user_id: uuid.UUID,
) -> Callable[[Request, AsyncSession], Awaitable[object | None]]:
    async def resolver(request: Request, session: AsyncSession) -> WebPrincipal | None:
        return WebPrincipal(
            user_id=user_id,
            agri_id="AG00000001",
            roles=(),
            session_id=None,
            fingerprint=None,
        )

    return cast(Callable[[Request, AsyncSession], Awaitable[object | None]], resolver)


def _api_for(db_session: AsyncSession, user_id: uuid.UUID) -> httpx.AsyncClient:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver_for(user_id))
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="https://id.test")


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with _api_for(db_session, USER_A) as client:
        yield client


def _sub_body(endpoint: str = ENDPOINT_1) -> dict[str, object]:
    return {"endpoint": endpoint, "keys": {"p256dh": "pkey", "auth": "akey"}, "ua_label": "Chrome"}


async def _enable_push_flag(session: AsyncSession) -> None:
    flag = await session.get(FeatureFlag, "notify.push_enabled")
    assert flag is not None
    flag.enabled = True
    await session.flush()


def _push_request(user_id: uuid.UUID = USER_A) -> NotifyRequest:
    return NotifyRequest(
        user_id=user_id,
        template_key="lead_received",
        payload={"business_name": "E2E Dairy", "inquiry_type": "milk"},
        locale="en",
        channels=frozenset({"push"}),
    )


def _subscription(user_id: uuid.UUID, endpoint: str) -> PushSubscription:
    return PushSubscription(user_id=user_id, endpoint=endpoint, p256dh="p", auth="a")


# ---- subscriptions API ----


async def test_subscribe_upserts_by_endpoint(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    assert (await api.post("/notify/push/subscriptions", json=_sub_body())).status_code == 200
    body = _sub_body() | {"keys": {"p256dh": "pkey2", "auth": "akey2"}}
    assert (await api.post("/notify/push/subscriptions", json=body)).status_code == 200
    rows = (await db_session.scalars(select(PushSubscription))).all()
    assert len(rows) == 1
    assert rows[0].p256dh == "pkey2"
    assert rows[0].user_id == USER_A


async def test_unsubscribe_deletes_own_row(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(_subscription(USER_A, ENDPOINT_1))
    await db_session.flush()
    res = await api.request("DELETE", "/notify/push/subscriptions", json={"endpoint": ENDPOINT_1})
    assert res.status_code == 200
    assert (await db_session.scalars(select(PushSubscription))).all() == []


async def test_unsubscribe_ignores_foreign_row(db_session: AsyncSession) -> None:
    db_session.add(_subscription(USER_A, ENDPOINT_1))
    await db_session.flush()
    async with _api_for(db_session, USER_B) as api_b:
        res = await api_b.request(
            "DELETE", "/notify/push/subscriptions", json={"endpoint": ENDPOINT_1}
        )
    assert res.status_code == 404
    assert len((await db_session.scalars(select(PushSubscription))).all()) == 1


async def test_preferences_lists_and_toggles_push(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    listed = (await api.get("/notify/preferences")).json()["items"]
    assert {item["channel"] for item in listed} == {"sms", "email", "push"}
    res = await api.put("/notify/preferences", json={"channel": "push", "enabled": False})
    assert res.status_code == 200
    listed = (await api.get("/notify/preferences")).json()["items"]
    assert {"channel": "push", "enabled": False} in listed


# ---- dispatch pipeline ----


async def test_dispatch_push_sends_to_all_subscriptions(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    await _enable_push_flag(db_session)
    db_session.add_all([_subscription(USER_A, ENDPOINT_1), _subscription(USER_A, ENDPOINT_2)])
    await db_session.flush()
    await dispatch(db_session, _push_request(), now=NOW)
    assert {e for e, _t, _b in MockPushDriver.outbox} == {ENDPOINT_1, ENDPOINT_2}
    title = MockPushDriver.outbox[0][1]
    assert title == "New enquiry — E2E Dairy"  # rendered subject IS the title
    deliveries = (await db_session.scalars(select(Delivery))).all()
    assert {d.status for d in deliveries} == {"sent"}
    assert {d.channel for d in deliveries} == {"push"}


async def test_dispatch_push_flag_off_drops(db_session: AsyncSession, otp_redis: Redis) -> None:
    db_session.add(_subscription(USER_A, ENDPOINT_1))
    await db_session.flush()
    await dispatch(db_session, _push_request(), now=NOW)
    assert MockPushDriver.outbox == []
    assert (await db_session.scalars(select(Delivery))).all() == []


async def test_dispatch_push_preference_off_drops(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    await _enable_push_flag(db_session)
    db_session.add(_subscription(USER_A, ENDPOINT_1))
    db_session.add(Preference(user_id=USER_A, channel="push", enabled=False))
    await db_session.flush()
    await dispatch(db_session, _push_request(), now=NOW)
    assert MockPushDriver.outbox == []
    assert (await db_session.scalars(select(Delivery))).all() == []


async def test_dispatch_push_no_subscription_drops(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    await _enable_push_flag(db_session)
    await dispatch(db_session, _push_request(), now=NOW)
    assert MockPushDriver.outbox == []
    assert (await db_session.scalars(select(Delivery))).all() == []


async def test_expired_subscription_pruned(
    db_session: AsyncSession, otp_redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _enable_push_flag(db_session)
    db_session.add(_subscription(USER_A, ENDPOINT_1))
    await db_session.flush()

    async def gone(
        self: object, subscription_info: dict[str, object], title: str, body: str
    ) -> str | None:
        raise ExpiredSubscriptionError

    monkeypatch.setattr(MockPushDriver, "send", gone)
    await dispatch(db_session, _push_request(), now=NOW)
    assert (await db_session.scalars(select(PushSubscription))).all() == []
    delivery = (await db_session.scalars(select(Delivery))).one()
    assert delivery.status == "dead"


async def test_transient_push_failure_schedules_retry(
    db_session: AsyncSession, otp_redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _enable_push_flag(db_session)
    db_session.add(_subscription(USER_A, ENDPOINT_1))
    await db_session.flush()

    async def boom(
        self: object, subscription_info: dict[str, object], title: str, body: str
    ) -> str | None:
        raise RuntimeError("provider down")

    monkeypatch.setattr(MockPushDriver, "send", boom)
    await dispatch(db_session, _push_request(), now=NOW)
    delivery = (await db_session.scalars(select(Delivery))).one()
    assert delivery.status == "failed"
    assert delivery.attempts == 1
    assert delivery.next_attempt_at is not None


# ---- SSRF gate (push endpoints are URLs the SERVER later POSTs to) ----


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "https://127.0.0.1:8000/internal",  # loopback
        "https://attacker.example/collect",  # not a push service
        "http://fcm.googleapis.com/fcm/send/x",  # right host, wrong scheme
        "https://fcm.googleapis.com.evil.test/x",  # suffix-confusion host
    ],
)
async def test_subscribe_rejects_non_push_service_endpoints(
    api: httpx.AsyncClient, db_session: AsyncSession, endpoint: str
) -> None:
    res = await api.post("/notify/push/subscriptions", json=_sub_body(endpoint))
    assert res.status_code == 422
    assert (await db_session.scalars(select(PushSubscription))).all() == []


async def test_disallowed_stored_endpoint_is_pruned_without_sending(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    """Defence in depth: a row written before the allowlist existed must
    never become an outbound request when the flag is flipped on."""
    await _enable_push_flag(db_session)
    db_session.add(_subscription(USER_A, "https://169.254.169.254/hijack"))
    await db_session.flush()
    await dispatch(db_session, _push_request(), now=NOW)
    assert MockPushDriver.outbox == []  # no send attempted
    assert (await db_session.scalars(select(PushSubscription))).all() == []  # pruned
    delivery = (await db_session.scalars(select(Delivery))).one()
    assert delivery.status == "dead"
    assert delivery.last_error == "endpoint_not_allowed"
