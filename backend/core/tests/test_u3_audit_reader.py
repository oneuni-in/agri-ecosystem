"""U3 audit reader (Group C). The reader D12's hash-chained log never had.

Two contracts pinned:
  1. FILTERING: by actor / action / entity returns only matching rows, newest
     first, keyset-paginated — never a leak of the whole log.
  2. APPEND-ONLY: the surface is read-only. There is NO purge / edit / delete
     route — POST/PUT/DELETE on /admin/audit do not exist (405). The
     Mattress.in blueprint's date-range purge is deliberately not ported.
"""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared.audit import audit
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

ADMIN_A = uuid.uuid4()
ADMIN_B = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _staff() -> dict[str, str]:
    return {"x-test-user": str(uuid.uuid4()), "x-test-roles": "staff"}


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


async def _seed(session: AsyncSession) -> None:
    await audit(
        session,
        action="directory.business_suspended",
        actor_user_id=ADMIN_A,
        target_type="business",
        target_id="biz-1",
        metadata={"reason": "spam"},
    )
    await audit(
        session,
        action="coins.manual_adjust",
        actor_user_id=ADMIN_B,
        target_type="user",
        target_id="user-9",
        metadata={"delta": 100},
    )
    await audit(
        session,
        action="directory.business_reinstated",
        actor_user_id=ADMIN_A,
        target_type="business",
        target_id="biz-1",
        metadata={"note": "appeal upheld"},
    )
    await session.commit()


async def test_filter_by_actor_returns_only_that_actor(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _seed(session)
    r = await http.get("/admin/audit", params={"actor": str(ADMIN_A)}, headers=_staff())
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    assert {i["actor_user_id"] for i in items} == {str(ADMIN_A)}
    # newest first — reinstate (seeded last) leads
    assert items[0]["action"] == "directory.business_reinstated"
    assert items[0]["metadata"]["note"] == "appeal upheld"


async def test_filter_by_action_and_entity(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _seed(session)
    by_action = await http.get(
        "/admin/audit", params={"action": "coins.manual_adjust"}, headers=_staff()
    )
    assert [i["action"] for i in by_action.json()["items"]] == ["coins.manual_adjust"]
    by_entity = await http.get(
        "/admin/audit",
        params={"entity_type": "business", "entity_id": "biz-1"},
        headers=_staff(),
    )
    actions = {i["action"] for i in by_entity.json()["items"]}
    assert actions == {"directory.business_suspended", "directory.business_reinstated"}


async def test_unfiltered_returns_the_whole_timeline_newest_first(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _seed(session)
    r = await http.get("/admin/audit", headers=_staff())
    items = r.json()["items"]
    assert len(items) >= 3
    times = [i["created_at"] for i in items]
    assert times == sorted(times, reverse=True)


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
async def test_audit_log_has_no_write_route(
    api: tuple[httpx.AsyncClient, AsyncSession], method: str
) -> None:
    """Append-only, non-negotiable: no purge/edit/delete exists on the reader.
    A write method resolves to 405 (route path known, method not allowed) —
    never 200, never a mutation."""
    http, _ = api
    r = await http.request(method, "/admin/audit", headers=_staff())
    assert r.status_code == 405
