"""D22 Gate 3 full-loop E2E: register -> claim a business -> billing
subscribe-path reachable but GATED (billing flag off) -> receive a routed
lead -> respond. One cohesive pass through the real API spanning three modules
(directory claims, billing, leads), the exact loop the gate mandates.

Follows the test_claim_e2e.py pattern: a header-driven principal resolver, an
in-memory object store, and a capturing publish so cross-module events are
asserted without a live Redis hop."""

import uuid
from collections.abc import AsyncIterator
from io import BytesIO
from typing import Any

import httpx
import pytest
from fastapi import Request
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import service as directory_service
from modules.directory.models import Business
from shared import storage
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

OWNER = uuid.uuid4()  # registers, then claims and runs the business
STAFF = uuid.uuid4()  # approves the claim
BUYER = uuid.uuid4()  # a signed-in buyer who sends a lead
PINCODE = "641001"  # D18-mandated pincode


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str = "user") -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


@pytest.fixture
async def api(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession, list[tuple[str, dict[str, Any]]]]]:
    app = create_app()
    store: dict[str, bytes] = {}
    published: list[tuple[str, dict[str, Any]]] = []

    async def fake_put(key: str, data: bytes, content_type: str) -> None:
        store[key] = data

    async def fake_get(key: str) -> bytes:
        return store[key]

    async def fake_publish(stream: str, event_type: str, payload: dict[str, Any]) -> str:
        published.append((event_type, payload))
        return "1-0"

    monkeypatch.setattr(storage, "put_object", fake_put)
    monkeypatch.setattr(storage, "get_object", fake_get)
    monkeypatch.setattr("modules.directory.admin_router.publish", fake_publish)
    monkeypatch.setattr("modules.directory.leads_router.publish", fake_publish)

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


async def test_full_loop_claim_billing_gated_lead_respond(
    api: tuple[httpx.AsyncClient, AsyncSession, list[tuple[str, dict[str, Any]]]],
) -> None:
    http, session, published = api

    # 1. a seeded, unclaimed business at 641001
    business = Business(
        owner_user_id=None,
        name="Kovai Agro Stores",
        slug=f"kovai-{uuid.uuid4().hex[:10]}",
        type="shop",
        primary_pincode=PINCODE,
    )
    session.add(business)
    await session.flush()
    await session.refresh(business)

    # 2. OWNER claims it with evidence; STAFF approves in the queue
    buf = BytesIO()
    Image.new("RGB", (24, 24), "green").save(buf, format="JPEG")
    created = await http.post(
        f"/directory/businesses/{business.id}/claim",
        files=[("files", ("shopfront.jpg", buf.getvalue(), "image/jpeg"))],
        headers=_as(OWNER),
    )
    assert created.status_code == 201
    claim_id = created.json()["id"]
    approved = await http.post(
        f"/admin/directory/claims/{claim_id}/approve",
        json={"note": "verified against shop photo"},
        headers=_as(STAFF, "staff"),
    )
    assert approved.status_code == 200
    await session.refresh(business)
    assert business.owner_user_id == OWNER  # ownership transferred

    # 3. the billing subscribe path is REACHABLE but GATED (flag off -> 404,
    #    never 403 - the surface does not exist while dark).
    gated_read = await http.get("/billing/subscription", headers=_as(OWNER))
    assert gated_read.status_code == 404
    gated_create = await http.post(
        "/billing/subscriptions",
        json={"tier": "growth", "business_id": str(business.id)},
        headers=_as(OWNER),
    )
    assert gated_create.status_code == 404

    # 4. owner sets coverage so inquiries in 641001 route to this business
    await directory_service.set_coverage(
        session, owner_user_id=OWNER, business_id=business.id, pincodes=[PINCODE]
    )
    await session.commit()

    # 5. a signed-in buyer sends a lead -> routed to the owner's business;
    #    lead.created is emitted naming the owner as recipient.
    inquiry = await http.post(
        "/leads/inquiries",
        json={
            "type": "contact",
            "business_id": str(business.id),
            "pincode": PINCODE,
            "payload": {"message": "Do you deliver cattle feed?"},
        },
        headers=_as(BUYER),
    )
    assert inquiry.status_code == 201
    inquiry_id = inquiry.json()["id"]
    lead_created = [p for (t, p) in published if t == "lead.created"]
    assert lead_created and lead_created[0]["user_id"] == str(OWNER)

    # 6. the owner sees the routed lead in the inbox
    inbox = await http.get(
        "/leads/inbox", params={"business_id": str(business.id)}, headers=_as(OWNER)
    )
    assert inbox.status_code == 200
    items = inbox.json()["items"]
    assert len(items) == 1 and items[0]["id"] == inquiry_id

    # 7. the owner responds -> 201, lead.responded emitted back to the buyer
    response = await http.post(
        f"/leads/inquiries/{inquiry_id}/responses",
        json={"body": "Yes, we deliver within 5km of Gandhipuram."},
        headers=_as(OWNER),
    )
    assert response.status_code == 201
    lead_responded = [p for (t, p) in published if t == "lead.responded"]
    assert lead_responded and lead_responded[0]["user_id"] == str(BUYER)
