"""A-U4b C1: the ingest-health admin read surfaces.

Both engines write an ingest_runs ledger (ADR-0012) precisely so a missed
day is distinguishable from a quiet source — but until these routes,
nothing read either table. Contracts pinned here:

  1. Staff see the run ledger newest-first from BOTH routes.
  2. An ordinary user gets 403 from both (require_permission, not a body
     check).
  3. A malformed cursor fails in each module's OWN idiom: 400 "invalid
     cursor" on market (the ops idiom), 422 "invalid_cursor" on content.
  4. The cursor round-trips: page two starts where page one stopped.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.content.models import IngestRun as ContentIngestRun
from modules.market_data.models import IngestRun as MarketIngestRun
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _staff() -> dict[str, str]:
    return {"x-test-user": str(uuid.uuid4()), "x-test-roles": "staff"}


def _user() -> dict[str, str]:
    return {"x-test-user": str(uuid.uuid4()), "x-test-roles": "user"}


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


async def _seed_market(session: AsyncSession, n: int = 3) -> None:
    base = datetime(2026, 8, 18, 6, 0, tzinfo=UTC)
    for i in range(n):
        session.add(
            MarketIngestRun(
                started_at=base + timedelta(days=i),
                finished_at=base + timedelta(days=i, minutes=2),
                outcome="ok" if i % 2 == 0 else "fetch_failed",
                fetched=10 + i,
                written=8 + i,
                quarantined=1,
                error=None if i % 2 == 0 else "boom",
            )
        )
        # flush per row so UUIDv7 ids strictly increase in insert order
        await session.flush()
    await session.commit()


async def _seed_content(session: AsyncSession, n: int = 3) -> None:
    base = datetime(2026, 8, 18, 7, 0, tzinfo=UTC)
    for i in range(n):
        session.add(
            ContentIngestRun(
                source_slug=f"src-{i}",
                started_at=base + timedelta(days=i),
                finished_at=base + timedelta(days=i, minutes=1),
                outcome="ok",
                fetched=5 + i,
                written=4 + i,
                duplicates=1,
                skipped=0,
            )
        )
        await session.flush()
    await session.commit()


async def test_staff_sees_market_runs_newest_first(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _seed_market(session)
    r = await http.get("/admin/market/ingest-runs", headers=_staff())
    assert r.status_code == 200
    body = r.json()
    items = body["items"]
    assert len(items) >= 3
    # newest first: UUIDv7 keyset descending == reverse insert order
    starts = [i["started_at"] for i in items[:3]]
    assert starts == sorted(starts, reverse=True)
    newest = items[0]
    assert set(newest) >= {
        "id",
        "source",
        "started_at",
        "finished_at",
        "outcome",
        "fetched",
        "written",
        "quarantined",
        "newest_arrival_date",
        "error",
    }
    assert newest["source"] == "agmarknet"
    assert "next_cursor" in body


async def test_staff_sees_content_runs_newest_first(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _seed_content(session)
    r = await http.get("/admin/content/ingest-runs", headers=_staff())
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 3
    starts = [i["started_at"] for i in items[:3]]
    assert starts == sorted(starts, reverse=True)
    assert items[0]["source_slug"] == "src-2"  # seeded last -> leads
    assert set(items[0]) >= {
        "id",
        "source_slug",
        "started_at",
        "finished_at",
        "outcome",
        "fetched",
        "written",
        "duplicates",
        "skipped",
        "error",
    }


@pytest.mark.parametrize("path", ["/admin/market/ingest-runs", "/admin/content/ingest-runs"])
async def test_ordinary_user_is_403(api: tuple[httpx.AsyncClient, AsyncSession], path: str) -> None:
    http, _ = api
    r = await http.get(path, headers=_user())
    assert r.status_code == 403
    assert r.json()["detail"] == "missing_permission"


async def test_invalid_cursor_speaks_each_modules_idiom(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Market inherits the ops idiom (400 "invalid cursor"); content keeps
    its own (422 "invalid_cursor"). Divergent on purpose — each route
    mirrors ITS module, and this test pins that they stay put."""
    http, _ = api
    market = await http.get(
        "/admin/market/ingest-runs", params={"cursor": "not-a-cursor"}, headers=_staff()
    )
    assert market.status_code == 400
    assert market.json()["detail"] == "invalid cursor"
    content = await http.get(
        "/admin/content/ingest-runs", params={"cursor": "not-a-cursor"}, headers=_staff()
    )
    assert content.status_code == 422
    assert content.json()["detail"] == "invalid_cursor"


async def test_market_cursor_round_trip(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _seed_market(session, n=5)
    first = await http.get("/admin/market/ingest-runs", params={"limit": 2}, headers=_staff())
    assert first.status_code == 200
    page1 = first.json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"]
    second = await http.get(
        "/admin/market/ingest-runs",
        params={"limit": 2, "cursor": page1["next_cursor"]},
        headers=_staff(),
    )
    assert second.status_code == 200
    page2 = second.json()
    assert len(page2["items"]) == 2
    # no overlap, and strictly older than everything on page one
    ids1 = {i["id"] for i in page1["items"]}
    ids2 = {i["id"] for i in page2["items"]}
    assert ids1.isdisjoint(ids2)
    assert max(i["id"] for i in page2["items"]) < min(i["id"] for i in page1["items"])
