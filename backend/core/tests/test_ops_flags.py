"""Ops Console flags API: super_admin only, audited, cache-reset (D21 Task 11)."""

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
from shared.flags import flag_enabled
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


async def test_staff_list_403(api: httpx.AsyncClient) -> None:
    """Staff cannot list flags."""
    r = await api.get("/admin/ops/flags", headers=_as(ADMIN_ID, "staff"))
    assert r.status_code == 403


async def test_super_admin_list_200(api: httpx.AsyncClient) -> None:
    """Super admin can list all flags."""
    r = await api.get("/admin/ops/flags", headers=_as(ADMIN_ID, "super_admin"))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    items_by_key = {item["key"]: item for item in body["items"]}
    assert "ads_enabled" in items_by_key
    assert "billing_enabled" in items_by_key
    assert items_by_key["ads_enabled"]["enabled"] is False
    assert items_by_key["billing_enabled"]["enabled"] is False


async def test_super_admin_toggle_200_with_cache_reset(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """Super admin can toggle a flag, and cache is immediately reset."""
    # Toggle the flag
    r = await api.put(
        "/admin/ops/flags/ads_enabled",
        json={"enabled": True},
        headers=_as(ADMIN_ID, "super_admin"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "ads_enabled"
    assert body["enabled"] is True

    # Verify cache is reset: flag_enabled should return True immediately
    # (without the reset, it would be stale for up to 30s)
    is_enabled = await flag_enabled("ads_enabled", session=db_session)
    assert is_enabled is True


async def test_toggle_creates_audit_entry(api: httpx.AsyncClient, db_session: AsyncSession) -> None:
    """Flag toggle creates an audit entry."""
    # Toggle the flag
    r = await api.put(
        "/admin/ops/flags/ads_enabled",
        json={"enabled": True},
        headers=_as(ADMIN_ID, "super_admin"),
    )
    assert r.status_code == 200

    # Verify audit entry exists
    audit_entries = (
        await db_session.scalars(select(AuditEntry).where(AuditEntry.action == "ops.flag_changed"))
    ).all()
    assert len(audit_entries) == 1
    entry = audit_entries[0]
    assert entry.target_id == "ads_enabled"
    assert entry.target_type == "feature_flag"
    assert entry.meta == {"enabled": True}
    assert entry.actor_user_id == ADMIN_ID


async def test_staff_toggle_403(api: httpx.AsyncClient) -> None:
    """Staff cannot toggle flags."""
    r = await api.put(
        "/admin/ops/flags/ads_enabled",
        json={"enabled": True},
        headers=_as(ADMIN_ID, "staff"),
    )
    assert r.status_code == 403


async def test_toggle_unknown_key_404(api: httpx.AsyncClient, db_session: AsyncSession) -> None:
    """Toggling unknown key returns 404."""
    r = await api.put(
        "/admin/ops/flags/unknown_key",
        json={"enabled": True},
        headers=_as(ADMIN_ID, "super_admin"),
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "unknown_flag"
