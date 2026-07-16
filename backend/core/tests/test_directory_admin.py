"""D16 admin queues. Non-negotiable 2: every decision audit-logged with the
chain still clean. Non-negotiable 4: approve sets owner + verified in ONE
transaction. Role gate is raw roles (staff/super_admin), coins pattern."""

import uuid
from collections.abc import AsyncIterator
from io import BytesIO
from typing import Any

import httpx
import pytest
from fastapi import Request
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory.models import Business, Verification
from shared import storage
from shared.audit import verify_chain
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

CLAIMANT = uuid.uuid4()
ADMIN = uuid.uuid4()
PLAIN = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str = "user") -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


def _jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (24, 24), "red").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def object_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    store: dict[str, bytes] = {}

    async def fake_put(key: str, data: bytes, content_type: str) -> None:
        store[key] = data

    async def fake_get(key: str) -> bytes:
        return store[key]

    monkeypatch.setattr(storage, "put_object", fake_put)
    monkeypatch.setattr(storage, "get_object", fake_get)
    return store


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict[str, Any]]]:
    """Capture best-effort event publishes from the admin router."""
    events: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_publish(stream: str, event_type: str, payload: dict[str, Any]) -> str:
        events.append((stream, event_type, payload))
        return "1-0"

    monkeypatch.setattr("modules.directory.admin_router.publish", fake_publish)
    return events


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

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
        yield client, db_session


async def _pending_claim(
    http: httpx.AsyncClient, session: AsyncSession, name: str = "Seeded Farm"
) -> tuple[str, Business]:
    business = Business(
        owner_user_id=None,
        name=name,
        slug=f"seeded-{uuid.uuid4().hex[:10]}",
        type="farm",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    await session.refresh(business)
    created = await http.post(
        f"/directory/businesses/{business.id}/claim",
        files=[("files", ("doc.jpg", _jpeg(), "image/jpeg"))],
        headers=_as(CLAIMANT),
    )
    assert created.status_code == 201
    return created.json()["id"], business


async def test_admin_routes_are_role_gated(
    api: tuple[httpx.AsyncClient, AsyncSession],
    object_store: dict[str, bytes],
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    claim_id, _ = await _pending_claim(http, session)
    assert (await http.get("/admin/directory/claims")).status_code == 401
    assert (await http.get("/admin/directory/claims", headers=_as(PLAIN))).status_code == 403
    assert (
        await http.post(f"/admin/directory/claims/{claim_id}/approve", json={}, headers=_as(PLAIN))
    ).status_code == 403
    assert (
        await http.get("/admin/directory/claims", headers=_as(ADMIN, "staff"))
    ).status_code == 200


async def test_approve_sets_owner_verified_verification_audit_event(
    api: tuple[httpx.AsyncClient, AsyncSession],
    object_store: dict[str, bytes],
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    claim_id, business = await _pending_claim(http, session, "Anbu Seeds")
    response = await http.post(
        f"/admin/directory/claims/{claim_id}/approve",
        json={"note": "GST photo checks out"},
        headers=_as(ADMIN, "staff"),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    # non-negotiable 4: owner + verified set together
    await session.refresh(business)
    assert business.owner_user_id == CLAIMANT
    assert business.verification_status == "verified"
    # verification record written by the approval
    verification = await session.scalar(
        select(Verification).where(Verification.business_id == business.id)
    )
    assert verification is not None
    assert verification.method == "claim" and verification.status == "approved"
    # non-negotiable 2: audit entry exists and the chain is clean
    from shared.audit import AuditEntry

    entry = await session.scalar(
        select(AuditEntry).where(AuditEntry.action == "directory.claim_approved")
    )
    assert entry is not None
    assert entry.target_id == claim_id
    assert entry.meta["business_id"] == str(business.id)
    assert await verify_chain(session) == []
    # event published for coins + notify, business-scoped payload
    assert published == [
        (
            "directory",
            "business.claimed",
            {
                "user_id": str(CLAIMANT),
                "business_id": str(business.id),
                "vars": {"business_name": "Anbu Seeds"},
            },
        )
    ]


async def test_approve_is_single_shot_and_conflict_safe(
    api: tuple[httpx.AsyncClient, AsyncSession],
    object_store: dict[str, bytes],
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    claim_id, business = await _pending_claim(http, session)
    # a second pending claim from another user on the same business
    other = uuid.uuid4()
    second = await http.post(
        f"/directory/businesses/{business.id}/claim",
        files=[("files", ("doc.jpg", _jpeg(), "image/jpeg"))],
        headers=_as(other),
    )
    second_id = second.json()["id"]
    assert (
        await http.post(
            f"/admin/directory/claims/{claim_id}/approve", json={}, headers=_as(ADMIN, "staff")
        )
    ).status_code == 200
    # same claim again -> 409 already_decided
    again = await http.post(
        f"/admin/directory/claims/{claim_id}/approve", json={}, headers=_as(ADMIN, "staff")
    )
    assert again.status_code == 409
    assert again.json()["detail"] == "already_decided"
    # competing claim on a now-owned business -> 409 already_owned
    competing = await http.post(
        f"/admin/directory/claims/{second_id}/approve", json={}, headers=_as(ADMIN, "staff")
    )
    assert competing.status_code == 409
    assert competing.json()["detail"] == "already_owned"
    assert len(published) == 1  # exactly one business.claimed


async def test_reject_requires_note_and_notifies_with_reason(
    api: tuple[httpx.AsyncClient, AsyncSession],
    object_store: dict[str, bytes],
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    claim_id, business = await _pending_claim(http, session, "Fake Farm")
    no_note = await http.post(
        f"/admin/directory/claims/{claim_id}/reject", json={}, headers=_as(ADMIN, "staff")
    )
    assert no_note.status_code == 422
    response = await http.post(
        f"/admin/directory/claims/{claim_id}/reject",
        json={"note": "evidence is a stock photo"},
        headers=_as(ADMIN, "staff"),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    await session.refresh(business)
    assert business.owner_user_id is None  # untouched
    assert business.verification_status == "unverified"
    assert published == [
        (
            "directory",
            "directory.claim_rejected",
            {
                "user_id": str(CLAIMANT),
                "business_id": str(business.id),
                "vars": {"business_name": "Fake Farm", "reason": "evidence is a stock photo"},
            },
        )
    ]
    assert await verify_chain(session) == []


async def test_admin_queue_lists_and_evidence(
    api: tuple[httpx.AsyncClient, AsyncSession],
    object_store: dict[str, bytes],
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    claim_id, business = await _pending_claim(http, session, "Queue Farm")
    queue = await http.get("/admin/directory/claims", headers=_as(ADMIN, "staff"))
    assert queue.status_code == 200
    items = queue.json()["items"]
    assert [i["id"] for i in items] == [claim_id]
    assert items[0]["business_name"] == "Queue Farm"
    evidence = await http.get(
        f"/admin/directory/claims/{claim_id}/evidence/0", headers=_as(ADMIN, "staff")
    )
    assert evidence.status_code == 200
    assert evidence.content[:3] == b"\xff\xd8\xff"
    # plain users can't read evidence through the admin route
    assert (
        await http.get(f"/admin/directory/claims/{claim_id}/evidence/0", headers=_as(PLAIN))
    ).status_code == 403
