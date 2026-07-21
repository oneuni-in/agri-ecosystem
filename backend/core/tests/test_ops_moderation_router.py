"""modules/ops moderation fan-in: role gate, delegation to registered
sources, and the single commit -> best-effort-publish choreography."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared.db import get_session
from shared.moderation import (
    DecisionConflictError,
    ItemNotFoundError,
    ModDecision,
    ModItem,
    PendingEvent,
    register_moderation_source,
)
from shared.pagination import Page
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

ADMIN = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str) -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


def _item(item_id: uuid.UUID | None = None) -> ModItem:
    return ModItem(
        type_key="fake",
        id=item_id or uuid.uuid4(),
        created_at=datetime.now(UTC),
        title="Fake item",
        summary="summary",
        payload={"k": "v"},
    )


class FakeSource:
    type_key = "fake"

    def __init__(self) -> None:
        self.approved: list[uuid.UUID] = []
        self.raise_conflict = False

    async def count_pending(self, session: AsyncSession) -> int:
        return 3

    async def list_pending(self, session, *, cursor, limit):  # type: ignore[no-untyped-def]
        return Page(items=[_item()], next_cursor=None)

    async def approve(self, session, *, item_id, actor_user_id, note, ip):  # type: ignore[no-untyped-def]
        if self.raise_conflict:
            raise DecisionConflictError("already_decided")
        if str(item_id).endswith("0000"):
            raise ItemNotFoundError(str(item_id))
        self.approved.append(item_id)
        return ModDecision(
            item=_item(item_id),
            events=(PendingEvent("test-stream", "fake.approved", {"id": str(item_id)}),),
        )

    async def reject(self, session, *, item_id, actor_user_id, note, ip):  # type: ignore[no-untyped-def]
        return ModDecision(item=_item(item_id), events=())


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, FakeSource]]:
    fake = FakeSource()
    app = create_app()
    register_moderation_source(fake)  # after create_app: replaces nothing, adds "fake"

    async def _resolver(request: Request, session: AsyncSession) -> _Principal | None:
        header = request.headers.get("x-test-user")
        if header is None:
            return None
        return _Principal(
            uuid.UUID(header), tuple(request.headers.get("x-test-roles", "user").split(","))
        )

    register_principal_resolver(_resolver)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake


async def test_non_staff_403(api: tuple[httpx.AsyncClient, FakeSource]) -> None:
    client, _ = api
    r = await client.get("/admin/moderation/summary", headers=_as(ADMIN, "user"))
    assert r.status_code == 403


async def test_summary_counts_all_sources(api: tuple[httpx.AsyncClient, FakeSource]) -> None:
    client, _ = api
    r = await client.get("/admin/moderation/summary", headers=_as(ADMIN, "staff"))
    assert r.status_code == 200
    assert r.json()["counts"]["fake"] == 3


async def test_queue_lists_typed_items(api: tuple[httpx.AsyncClient, FakeSource]) -> None:
    client, _ = api
    r = await client.get("/admin/moderation/queue?type=fake", headers=_as(ADMIN, "staff"))
    assert r.status_code == 200
    body = r.json()
    assert body["items"][0]["type_key"] == "fake"
    assert body["items"][0]["payload"] == {"k": "v"}


async def test_queue_unknown_type_404(api: tuple[httpx.AsyncClient, FakeSource]) -> None:
    client, _ = api
    r = await client.get("/admin/moderation/queue?type=nope", headers=_as(ADMIN, "staff"))
    assert r.status_code == 404


async def test_approve_delegates_and_returns_item(
    api: tuple[httpx.AsyncClient, FakeSource],
) -> None:
    client, fake = api
    item_id = uuid.uuid4()
    r = await client.post(
        f"/admin/moderation/fake/{item_id}/approve",
        json={"note": "ok"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200
    assert fake.approved == [item_id]
    assert r.json()["id"] == str(item_id)


async def test_approve_conflict_409(api: tuple[httpx.AsyncClient, FakeSource]) -> None:
    client, fake = api
    fake.raise_conflict = True
    r = await client.post(
        f"/admin/moderation/fake/{uuid.uuid4()}/approve",
        json={},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "already_decided"


async def test_approve_missing_404(api: tuple[httpx.AsyncClient, FakeSource]) -> None:
    client, _ = api
    missing = uuid.UUID("018f0000-0000-7000-8000-000000000000")
    r = await client.post(
        f"/admin/moderation/fake/{missing}/approve", json={}, headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 404


async def test_reject_requires_note(api: tuple[httpx.AsyncClient, FakeSource]) -> None:
    client, _ = api
    r = await client.post(
        f"/admin/moderation/fake/{uuid.uuid4()}/reject", json={}, headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 422
