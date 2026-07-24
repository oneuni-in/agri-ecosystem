"""Post-my-need API (D25): authed fan-out post to ALL covering vendors,
my-needs view with per-vendor routes/responses, fulfill/close transitions.
Scaffold mirrors test_leads_router.py (client fixture + x-test-user
principal resolver, published fixture monkeypatching the router's publish)."""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import needs_service, service
from modules.directory.leads_models import Inquiry, InquiryResponse, Need
from modules.directory.models import Business, BusinessCoverage
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

PINCODE = "641001"  # non-negotiable 1 mandates this exact pincode

GOOD_PAYLOAD: dict[str, Any] = {
    "qty_liters": "1",
    "milk_type": "cow",
    "schedule": "daily",
    "delivery_time": "morning",
}


class _Principal:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.roles = ("user",)


def _as(user_id: uuid.UUID) -> dict[str, str]:
    return {"x-test-user": str(user_id)}


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict[str, Any]]]:
    events: list[tuple[str, str, dict[str, Any]]] = []

    async def _fake_publish(stream: str, event_type: str, payload: dict[str, Any]) -> str:
        events.append((stream, event_type, payload))
        return "1-1"

    monkeypatch.setattr("modules.directory.needs_router.publish", _fake_publish)
    return events


@pytest.fixture
def no_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass the Redis daily cap in tests that aren't about the cap."""

    async def _allow(user_id: uuid.UUID, *, now: datetime) -> None:
        return None

    monkeypatch.setattr(needs_service, "claim_need_slot", _allow)


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        return _Principal(uuid.UUID(header)) if header else None

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as http:
        yield http


async def _mk_business_with_coverage(
    session: AsyncSession, pincode: str, *, owner: uuid.UUID | None, name: str = "Vendor"
) -> Business:
    if owner is None:  # claimable: NULL owner, as seed scripts create (D16)
        business = Business(
            owner_user_id=None,
            name=name,
            slug=f"seeded-{uuid.uuid4().hex[:10]}",
            type="vendor",
            primary_pincode=pincode,
        )
        session.add(business)
        await session.flush()
        await session.refresh(business)
    else:
        business = await service.create_business(
            session, owner_user_id=owner, name=name, type_="vendor", primary_pincode=pincode
        )
    session.add(BusinessCoverage(business_id=business.id, pincode=pincode))
    await session.flush()
    return business


def _need_body(pincode: str = PINCODE, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"pincode": pincode, "payload": payload if payload is not None else GOOD_PAYLOAD}


async def test_post_need_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.post("/leads/needs", json=_need_body())
    assert response.status_code == 401


async def test_post_need_fans_out_only_to_covering(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tn_geo_sample: None,
    published: list[tuple[str, str, dict[str, Any]]],
    no_cap: None,
) -> None:
    owner_a = uuid.uuid4()
    a = await _mk_business_with_coverage(db_session, PINCODE, owner=owner_a, name="A")
    b = await _mk_business_with_coverage(db_session, PINCODE, owner=None, name="B")
    await _mk_business_with_coverage(db_session, "600001", owner=uuid.uuid4(), name="C")
    user = uuid.uuid4()

    response = await client.post("/leads/needs", json=_need_body(), headers=_as(user))
    assert response.status_code == 201
    body = response.json()
    assert body["routed_count"] == 2
    assert body["status"] == "open"
    assert body["has_voice"] is False

    children = list(
        await db_session.scalars(select(Inquiry).where(Inquiry.need_id == uuid.UUID(body["id"])))
    )
    assert {c.business_id for c in children} == {a.id, b.id}  # C never routed
    assert all(c.type == "milk_subscription" for c in children)
    assert all(c.from_user_id == user for c in children)
    assert all(c.payload["qty_liters"] == "1" for c in children)

    # lead.created published ONLY for A (B unclaimed - no owner to notify)
    assert [e[1] for e in published] == ["lead.created"]
    event = published[0][2]
    assert event["user_id"] == str(owner_a)
    assert event["business_id"] == str(a.id)
    assert event["vars"] == {"business_name": "A", "inquiry_type": "milk_subscription"}


async def test_post_need_bad_payload_422(client: httpx.AsyncClient, no_cap: None) -> None:
    response = await client.post(
        "/leads/needs",
        json=_need_body(payload={"qty_liters": "-1", "milk_type": "cow", "schedule": "daily"}),
        headers=_as(uuid.uuid4()),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_payload"


async def test_post_need_no_coverage_422(
    client: httpx.AsyncClient, tn_geo_sample: None, no_cap: None
) -> None:
    response = await client.post(
        "/leads/needs", json=_need_body(pincode="999999"), headers=_as(uuid.uuid4())
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "no_coverage"


async def test_post_need_cap_429(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _deny(user_id: uuid.UUID, *, now: datetime) -> None:
        raise needs_service.NeedCapExceededError()

    monkeypatch.setattr(needs_service, "claim_need_slot", _deny)
    response = await client.post("/leads/needs", json=_need_body(), headers=_as(uuid.uuid4()))
    assert response.status_code == 429
    assert response.json()["detail"] == "need_cap_exceeded"


async def test_post_need_cap_unavailable_503(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _down(user_id: uuid.UUID, *, now: datetime) -> None:
        raise needs_service.NeedsUnavailableError()

    monkeypatch.setattr(needs_service, "claim_need_slot", _down)
    response = await client.post("/leads/needs", json=_need_body(), headers=_as(uuid.uuid4()))
    assert response.status_code == 503
    assert response.json()["detail"] == "need_post_unavailable"


async def test_mine_lists_routes_and_responses(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tn_geo_sample: None,
    published: list[tuple[str, str, dict[str, Any]]],
    no_cap: None,
) -> None:
    vendor_owner = uuid.uuid4()
    vendor = await _mk_business_with_coverage(
        db_session, PINCODE, owner=vendor_owner, name="Dairy Farm"
    )
    user = uuid.uuid4()
    posted = await client.post("/leads/needs", json=_need_body(), headers=_as(user))
    assert posted.status_code == 201
    need_id = uuid.UUID(posted.json()["id"])

    child = await db_session.scalar(select(Inquiry).where(Inquiry.need_id == need_id))
    assert child is not None
    db_session.add(
        InquiryResponse(inquiry_id=child.id, business_user_id=vendor_owner, body="Daily 6am works.")
    )
    child.status = "responded"
    await db_session.flush()

    mine = await client.get("/leads/needs/mine", headers=_as(user))
    assert mine.status_code == 200
    items = mine.json()["items"]
    assert len(items) == 1
    need_out = items[0]
    assert need_out["status"] == "open"
    assert need_out["routed_count"] == 1
    route = need_out["routes"][0]
    assert route["business_id"] == str(vendor.id)
    assert route["business_name"] == "Dairy Farm"
    assert route["status"] == "responded"
    assert route["responses"][0]["body"] == "Daily 6am works."

    # someone else sees nothing
    other = await client.get("/leads/needs/mine", headers=_as(uuid.uuid4()))
    assert other.json()["items"] == []


async def test_fulfill_closes_children_and_repeat_409(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tn_geo_sample: None,
    published: list[tuple[str, str, dict[str, Any]]],
    no_cap: None,
) -> None:
    vendor = await _mk_business_with_coverage(
        db_session, PINCODE, owner=uuid.uuid4(), name="Dairy Farm"
    )
    user = uuid.uuid4()
    posted = await client.post("/leads/needs", json=_need_body(), headers=_as(user))
    need_id = posted.json()["id"]

    fulfilled = await client.post(
        f"/leads/needs/{need_id}/fulfill",
        json={"business_id": str(vendor.id)},
        headers=_as(user),
    )
    assert fulfilled.status_code == 200
    body = fulfilled.json()
    assert body["status"] == "fulfilled"
    assert body["accepted_business_id"] == str(vendor.id)

    children = list(
        await db_session.scalars(select(Inquiry).where(Inquiry.need_id == uuid.UUID(need_id)))
    )
    assert children and all(c.status == "closed" for c in children)

    again = await client.post(f"/leads/needs/{need_id}/fulfill", json={}, headers=_as(user))
    assert again.status_code == 409
    assert again.json()["detail"] == "need_closed"


async def test_close_need(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tn_geo_sample: None,
    published: list[tuple[str, str, dict[str, Any]]],
    no_cap: None,
) -> None:
    await _mk_business_with_coverage(db_session, PINCODE, owner=uuid.uuid4())
    user = uuid.uuid4()
    posted = await client.post("/leads/needs", json=_need_body(), headers=_as(user))
    need_id = posted.json()["id"]
    closed = await client.post(f"/leads/needs/{need_id}/close", headers=_as(user))
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["accepted_business_id"] is None


async def test_fulfill_idor_404(
    client: httpx.AsyncClient, db_session: AsyncSession, no_cap: None
) -> None:
    user = uuid.uuid4()
    need = Need(from_user_id=user, pincode=PINCODE, payload={})
    db_session.add(need)
    await db_session.flush()
    response = await client.post(
        f"/leads/needs/{need.id}/fulfill", json={}, headers=_as(uuid.uuid4())
    )
    assert response.status_code == 404


async def test_mine_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.get("/leads/needs/mine")
    assert response.status_code == 401
