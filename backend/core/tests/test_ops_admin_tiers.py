"""Ops Console pincode-tier endpoints (M4 Task 7): distribution, lookup,
admin override. Mirrors test_ops_flags.py's app/client/role-header fixtures."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared.audit import AuditEntry
from shared.db import get_session
from shared.geo.models import PincodeTier, PincodeTierHistory
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

ADMIN_ID = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str) -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

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
        yield client


async def _seed_three(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            PincodeTier(
                pincode="641001",
                population=150000,
                population_grade="town",
                tier=2,
                method="population",
            ),
            PincodeTier(
                pincode="641002",
                population=5000,
                population_grade="village",
                tier=4,
                method="population",
            ),
            PincodeTier(
                pincode="641003",
                population=200,
                population_grade="village",
                tier=5,
                method="population+users",
            ),
        ]
    )
    await db_session.flush()


async def test_distribution_staff_200_zero_filled_and_counted(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_three(db_session)
    r = await api.get("/admin/ops/pincode-tiers/distribution", headers=_as(ADMIN_ID, "staff"))
    assert r.status_code == 200
    body = r.json()
    buckets_by_tier = {b["tier"]: b["count"] for b in body["buckets"]}
    assert buckets_by_tier == {1: 0, 2: 1, 3: 0, 4: 1, 5: 1}
    assert body["total"] == 3
    assert body["by_method"] == {"population": 2, "population+users": 1}


async def test_distribution_non_staff_403(api: httpx.AsyncClient) -> None:
    r = await api.get("/admin/ops/pincode-tiers/distribution", headers=_as(ADMIN_ID, "user"))
    assert r.status_code == 403


async def test_lookup_staff_200(api: httpx.AsyncClient, db_session: AsyncSession) -> None:
    await _seed_three(db_session)
    r = await api.get("/admin/ops/pincode-tiers/641001", headers=_as(ADMIN_ID, "staff"))
    assert r.status_code == 200
    body = r.json()
    assert body["pincode"] == "641001"
    assert body["tier"] == 2
    assert body["population"] == 150000
    assert body["user_count"] == 0
    assert body["method"] == "population"


async def test_lookup_unknown_pincode_404(api: httpx.AsyncClient) -> None:
    r = await api.get("/admin/ops/pincode-tiers/999999", headers=_as(ADMIN_ID, "staff"))
    assert r.status_code == 404
    assert r.json()["detail"] == "unknown pincode"


async def test_lookup_non_staff_403(api: httpx.AsyncClient) -> None:
    r = await api.get("/admin/ops/pincode-tiers/641001", headers=_as(ADMIN_ID, "user"))
    assert r.status_code == 403


async def test_override_staff_200_writes_history_and_audit(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_three(db_session)
    r = await api.post(
        "/admin/ops/pincode-tiers/641001",
        json={"tier": 1},
        headers=_as(ADMIN_ID, "staff"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pincode"] == "641001"
    assert body["tier"] == 1

    history = (
        await db_session.scalars(
            select(PincodeTierHistory).where(PincodeTierHistory.pincode == "641001")
        )
    ).all()
    assert len(history) == 1
    assert history[0].reason == "admin_override"
    assert history[0].old_tier == 2
    assert history[0].new_tier == 1

    audit_entries = (
        await db_session.scalars(select(AuditEntry).where(AuditEntry.action == "geo.tier_override"))
    ).all()
    assert len(audit_entries) == 1
    entry = audit_entries[0]
    assert entry.actor_user_id == ADMIN_ID
    assert entry.meta == {"pincode": "641001", "tier": 1}


async def test_override_non_staff_403(api: httpx.AsyncClient) -> None:
    r = await api.post(
        "/admin/ops/pincode-tiers/641001",
        json={"tier": 1},
        headers=_as(ADMIN_ID, "user"),
    )
    assert r.status_code == 403


async def test_override_invalid_tier_422(api: httpx.AsyncClient, db_session: AsyncSession) -> None:
    await _seed_three(db_session)
    r = await api.post(
        "/admin/ops/pincode-tiers/641001",
        json={"tier": 9},
        headers=_as(ADMIN_ID, "staff"),
    )
    assert r.status_code == 422


async def test_override_unknown_pincode_404(api: httpx.AsyncClient) -> None:
    r = await api.post(
        "/admin/ops/pincode-tiers/999999",
        json={"tier": 1},
        headers=_as(ADMIN_ID, "staff"),
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "unknown pincode"
