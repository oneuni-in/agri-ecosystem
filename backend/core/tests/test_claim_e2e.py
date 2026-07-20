"""D16 DoD: claim -> admin approve -> coins award + verified badge + in-app
notification, end to end through the real API + worker/consumer handlers.
The event hop is exercised by feeding the ACTUAL published payload to both
consumers (test_coins_worker.py pattern - no Redis needed)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import httpx
import pytest
from fastapi import Request
from PIL import Image
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.coins import service as coins_service
from modules.coins.worker import handle_event as coins_handle
from modules.directory.models import Business
from modules.notify.consumers import handle_event as notify_handle
from modules.notify.models import Notification
from shared import storage
from shared.audit import verify_chain
from shared.db import get_session
from shared.events import Event
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

CLAIMANT = uuid.uuid4()
ADMIN = uuid.uuid4()
NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str = "user") -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


@pytest.fixture
async def api(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession, list[tuple[str, str, dict[str, Any]]]]]:
    app = create_app()
    store: dict[str, bytes] = {}
    published: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_put(key: str, data: bytes, content_type: str) -> None:
        store[key] = data

    async def fake_get(key: str) -> bytes:
        return store[key]

    async def fake_publish(stream: str, event_type: str, payload: dict[str, Any]) -> str:
        published.append((stream, event_type, payload))
        return "1-0"

    monkeypatch.setattr(storage, "put_object", fake_put)
    monkeypatch.setattr(storage, "get_object", fake_get)
    monkeypatch.setattr("modules.directory.admin_router.publish", fake_publish)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        if not header:
            return None
        roles = tuple((request.headers.get("x-test-roles") or "user").split(","))
        return _Principal(uuid.UUID(header), roles)

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client, db_session, published


async def test_claim_to_coins_badge_and_notification(
    api: tuple[httpx.AsyncClient, AsyncSession, list[tuple[str, str, dict[str, Any]]]],
    otp_redis: Redis,
) -> None:
    http, session, published = api
    # 1. a seeded, unclaimed business
    business = Business(
        owner_user_id=None,
        name="Kovai Agro Stores",
        slug=f"kovai-{uuid.uuid4().hex[:10]}",
        type="shop",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    await session.refresh(business)

    # 2. claimant submits a claim with evidence
    buf = BytesIO()
    Image.new("RGB", (24, 24), "green").save(buf, format="JPEG")
    created = await http.post(
        f"/directory/businesses/{business.id}/claim",
        files=[("files", ("shopfront.jpg", buf.getvalue(), "image/jpeg"))],
        headers=_as(CLAIMANT),
    )
    assert created.status_code == 201
    claim_id = created.json()["id"]

    # 3. staff approves in the queue
    approved = await http.post(
        f"/admin/directory/claims/{claim_id}/approve",
        json={"note": "verified against shop photo"},
        headers=_as(ADMIN, "staff"),
    )
    assert approved.status_code == 200

    # 4. badge + ownership landed atomically
    await session.refresh(business)
    assert business.owner_user_id == CLAIMANT
    assert business.verification_status == "verified"

    # 5. the published event drives BOTH consumers; replay proves idempotency.
    # A second, search-scoped business.updated rides alongside it (D19 Task 1)
    # but the coins/notify consumers only care about business.claimed.
    assert [e[1] for e in published] == ["business.claimed", "business.updated"]
    stream, event_type, payload = published[0]
    assert (stream, event_type) == ("directory", "business.claimed")
    event = Event(id="1-0", type=event_type, payload=payload)
    await coins_handle(session, event, now=NOW)
    await coins_handle(session, event, now=NOW)  # redelivery
    assert await coins_service.balance(session, CLAIMANT) == 200  # exactly once

    await notify_handle(session, event)
    notification = await session.scalar(
        select(Notification).where(Notification.user_id == CLAIMANT)
    )
    assert notification is not None

    # 6. the decision is on the audit chain, chain clean
    assert await verify_chain(session) == []
