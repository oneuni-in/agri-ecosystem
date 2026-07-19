"""Leads submission API (D18.B Task 7): guest-capable POST /leads/inquiries
via optional_auth attribution + coverage routing (Task 6) + best-effort
lead.created notify. Scaffold mirrors test_reviews_moderation.py (published
fixture monkeypatching the router's publish) and test_leads_routing.py
(_mk_business_with_coverage helper, tn_geo_sample for auto-route)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import service
from modules.directory.leads_models import Inquiry
from modules.directory.models import Business, BusinessCoverage
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio


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

    monkeypatch.setattr("modules.directory.leads_router.publish", _fake_publish)
    return events


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


async def _mk_business(
    session: AsyncSession, *, owner: uuid.UUID | None, name: str = "Vendor"
) -> Business:
    if owner is None:  # claimable: NULL owner, as seed scripts create (D16)
        business = Business(
            owner_user_id=None,
            name=name,
            slug=f"seeded-{uuid.uuid4().hex[:10]}",
            type="vendor",
            primary_pincode="641001",
        )
        session.add(business)
        await session.flush()
        await session.refresh(business)
        return business
    return await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode="641001"
    )


async def _mk_business_with_coverage(
    session: AsyncSession, pincode: str, *, owner: uuid.UUID | None, name: str = "Vendor"
) -> Business:
    business = await _mk_business(session, owner=owner, name=name)
    session.add(BusinessCoverage(business_id=business.id, pincode=pincode))
    await session.flush()
    return business


def _body(business_id: uuid.UUID | None, pincode: str, message: str = "Hello") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "contact",
        "pincode": pincode,
        "payload": {"message": message},
    }
    if business_id is not None:
        payload["business_id"] = str(business_id)
    return payload


async def test_guest_can_submit_contact_inquiry(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    b = await _mk_business_with_coverage(db_session, "641001", owner=uuid.uuid4())
    resp = await client.post(  # no auth header - guest
        "/leads/inquiries",
        json={
            "type": "contact",
            "business_id": str(b.id),
            "pincode": "641001",
            "payload": {"message": "Do you deliver on Sundays?"},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "new"
    assert body["business_id"] == str(b.id)
    assert body["business_name"] == b.name

    inquiry = await db_session.get(Inquiry, uuid.UUID(body["id"]))
    assert inquiry is not None
    assert inquiry.from_user_id is None  # guest

    assert published[0][:2] == ("directory", "lead.created")
    assert published[0][2]["user_id"] == str(b.owner_user_id)
    assert published[0][2]["inquiry_id"] == body["id"]
    assert published[0][2]["business_id"] == str(b.id)
    assert published[0][2]["vars"] == {"business_name": b.name, "inquiry_type": "contact"}


async def test_authed_submit_records_from_user_id(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    b = await _mk_business_with_coverage(db_session, "641001", owner=uuid.uuid4())
    author = uuid.uuid4()
    resp = await client.post(
        "/leads/inquiries",
        json=_body(b.id, "641001", "Any discounts on bulk orders?"),
        headers=_as(author),
    )
    assert resp.status_code == 201

    inquiry = await db_session.get(Inquiry, uuid.UUID(resp.json()["id"]))
    assert inquiry is not None
    assert inquiry.from_user_id == author


async def test_unclaimed_business_no_notification(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    b = await _mk_business_with_coverage(db_session, "641001", owner=None)
    assert b.owner_user_id is None

    resp = await client.post("/leads/inquiries", json=_body(b.id, "641001"))
    assert resp.status_code == 201
    assert published == []


async def test_business_not_covering_pincode_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    covered_elsewhere = await _mk_business_with_coverage(db_session, "600001", owner=uuid.uuid4())
    resp = await client.post("/leads/inquiries", json=_body(covered_elsewhere.id, "641001"))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "business_not_covered"


async def test_auto_route_no_coverage_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    resp = await client.post("/leads/inquiries", json=_body(None, "999999"))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "no_coverage"


async def test_milk_subscription_payload_validated(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    b = await _mk_business_with_coverage(db_session, "641001", owner=uuid.uuid4())
    bad = await client.post(
        "/leads/inquiries",
        json={
            "type": "milk_subscription",
            "business_id": str(b.id),
            "pincode": "641001",
            "payload": {"message": "wrong shape"},
        },
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "invalid_payload"

    good = await client.post(
        "/leads/inquiries",
        json={
            "type": "milk_subscription",
            "business_id": str(b.id),
            "pincode": "641001",
            "payload": {"qty_liters": "1.5", "milk_type": "cow", "schedule": "daily"},
        },
    )
    assert good.status_code == 201
    assert good.json()["type"] == "milk_subscription"


async def test_contact_payload_validated(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    b = await _mk_business_with_coverage(db_session, "641001", owner=uuid.uuid4())
    resp = await client.post(
        "/leads/inquiries",
        json={
            "type": "contact",
            "business_id": str(b.id),
            "pincode": "641001",
            "payload": {"message": ""},
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "invalid_payload"
