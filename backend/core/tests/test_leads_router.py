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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import service
from modules.directory.leads_models import Inquiry, InquiryResponse
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


async def _mk_inquiry(
    session: AsyncSession,
    business: Business,
    *,
    from_user_id: uuid.UUID | None = None,
    status: str = "new",
    message: str = "Hello",
) -> Inquiry:
    inquiry = Inquiry(
        type="contact",
        from_user_id=from_user_id,
        business_id=business.id,
        payload={"message": message},
        pincode=business.primary_pincode,
        category=None,
        status=status,
    )
    session.add(inquiry)
    await session.flush()
    await session.refresh(inquiry)
    return inquiry


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


async def test_inbox_requires_auth_and_ownership(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    business = await _mk_business(db_session, owner=owner)
    inquiry = await _mk_inquiry(db_session, business)

    unauth = await client.get("/leads/inbox", params={"business_id": str(business.id)})
    assert unauth.status_code == 401

    owned = await client.get(
        "/leads/inbox", params={"business_id": str(business.id)}, headers=_as(owner)
    )
    assert owned.status_code == 200
    body = owned.json()
    assert [i["id"] for i in body["items"]] == [str(inquiry.id)]

    denied = await client.get(
        "/leads/inbox", params={"business_id": str(business.id)}, headers=_as(other)
    )
    assert denied.status_code == 404


async def test_inbox_newest_first_keyset(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    owner = uuid.uuid4()
    business = await _mk_business(db_session, owner=owner)
    first = await _mk_inquiry(db_session, business, message="one")
    second = await _mk_inquiry(db_session, business, message="two")
    third = await _mk_inquiry(db_session, business, message="three")

    page1 = await client.get(
        "/leads/inbox",
        params={"business_id": str(business.id), "limit": 2},
        headers=_as(owner),
    )
    assert page1.status_code == 200
    body1 = page1.json()
    assert [i["id"] for i in body1["items"]] == [str(third.id), str(second.id)]
    assert body1["next_cursor"] is not None

    page2 = await client.get(
        "/leads/inbox",
        params={
            "business_id": str(business.id),
            "limit": 2,
            "cursor": body1["next_cursor"],
        },
        headers=_as(owner),
    )
    assert page2.status_code == 200
    body2 = page2.json()
    assert [i["id"] for i in body2["items"]] == [str(first.id)]
    assert body2["next_cursor"] is None


async def test_inbox_status_filter(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _mk_business(db_session, owner=owner)
    new_one = await _mk_inquiry(db_session, business, status="new")
    await _mk_inquiry(db_session, business, status="responded")

    resp = await client.get(
        "/leads/inbox",
        params={"business_id": str(business.id), "status": "new"},
        headers=_as(owner),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [i["id"] for i in body["items"]] == [str(new_one.id)]


async def test_respond_flow(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    owner = uuid.uuid4()
    submitter = uuid.uuid4()
    business = await _mk_business(db_session, owner=owner)
    inquiry = await _mk_inquiry(db_session, business, from_user_id=submitter)

    resp = await client.post(
        f"/leads/inquiries/{inquiry.id}/responses",
        json={"body": "Yes, we deliver on Sundays."},
        headers=_as(owner),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["inquiry_id"] == str(inquiry.id)
    assert body["business_user_id"] == str(owner)
    assert body["body"] == "Yes, we deliver on Sundays."

    await db_session.refresh(inquiry)
    assert inquiry.status == "responded"

    responded_events = [e for e in published if e[1] == "lead.responded"]
    assert len(responded_events) == 1
    assert responded_events[0][0] == "directory"
    assert responded_events[0][2]["user_id"] == str(submitter)
    assert responded_events[0][2]["inquiry_id"] == str(inquiry.id)
    assert responded_events[0][2]["vars"] == {"business_name": business.name}

    # guest inquiry (from_user_id None) -> respond publishes nothing
    guest_inquiry = await _mk_inquiry(db_session, business, from_user_id=None)
    resp2 = await client.post(
        f"/leads/inquiries/{guest_inquiry.id}/responses",
        json={"body": "Thanks for reaching out."},
        headers=_as(owner),
    )
    assert resp2.status_code == 201
    assert [e for e in published if e[1] == "lead.responded"] == responded_events


async def test_respond_to_closed_409(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    owner = uuid.uuid4()
    submitter = uuid.uuid4()
    business = await _mk_business(db_session, owner=owner)
    inquiry = await _mk_inquiry(db_session, business, from_user_id=submitter)

    closed = await client.post(f"/leads/inquiries/{inquiry.id}/close", headers=_as(owner))
    assert closed.status_code == 200

    resp = await client.post(
        f"/leads/inquiries/{inquiry.id}/responses",
        json={"body": "Too late."},
        headers=_as(owner),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "inquiry_closed"

    row = await db_session.scalar(
        select(InquiryResponse).where(InquiryResponse.inquiry_id == inquiry.id)
    )
    assert row is None
    assert [e for e in published if e[1] == "lead.responded"] == []


async def test_respond_idor(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    business = await _mk_business(db_session, owner=owner)
    inquiry = await _mk_inquiry(db_session, business)

    resp = await client.post(
        f"/leads/inquiries/{inquiry.id}/responses",
        json={"body": "Not yours to answer."},
        headers=_as(other),
    )
    assert resp.status_code == 404


async def test_close_inquiry(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _mk_business(db_session, owner=owner)
    inquiry = await _mk_inquiry(db_session, business)

    resp = await client.post(f"/leads/inquiries/{inquiry.id}/close", headers=_as(owner))
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"

    await db_session.refresh(inquiry)
    assert inquiry.status == "closed"


async def test_mine_lists_own_with_responses(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    owner = uuid.uuid4()
    submitter = uuid.uuid4()
    other = uuid.uuid4()
    business = await _mk_business(db_session, owner=owner)
    inquiry = await _mk_inquiry(db_session, business, from_user_id=submitter)

    respond = await client.post(
        f"/leads/inquiries/{inquiry.id}/responses",
        json={"body": "We deliver daily."},
        headers=_as(owner),
    )
    assert respond.status_code == 201

    mine = await client.get("/leads/mine", headers=_as(submitter))
    assert mine.status_code == 200
    mine_body = mine.json()
    assert [i["id"] for i in mine_body["items"]] == [str(inquiry.id)]
    responses = mine_body["items"][0]["responses"]
    assert len(responses) == 1
    assert responses[0]["body"] == "We deliver daily."

    empty = await client.get("/leads/mine", headers=_as(other))
    assert empty.status_code == 200
    assert empty.json()["items"] == []


async def test_inbox_stats(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _mk_business(db_session, owner=owner)
    responded_inquiry = await _mk_inquiry(db_session, business, from_user_id=uuid.uuid4())
    await _mk_inquiry(db_session, business)

    respond = await client.post(
        f"/leads/inquiries/{responded_inquiry.id}/responses",
        json={"body": "On it."},
        headers=_as(owner),
    )
    assert respond.status_code == 201

    resp = await client.get(
        "/leads/inbox/stats", params={"business_id": str(business.id)}, headers=_as(owner)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["responded"] == 1
    assert isinstance(body["avg_response_seconds"], int)
    assert body["avg_response_seconds"] >= 0
