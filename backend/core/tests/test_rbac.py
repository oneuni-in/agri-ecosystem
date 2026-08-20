"""D11.C: require_permission on three sample permissions, per-role denial,
cache freshness semantics."""

from collections.abc import AsyncIterator

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import User
from modules.identity.rbac import (
    permissions_for_roles,
    require_permission,
    reset_permission_cache,
)
from modules.identity.service import assign_role
from shared.db import get_session
from shared.security import SecureRouter
from tests.conftest import RbacMatrix
from tests.test_session_router import UA, _login

sample_router = SecureRouter(prefix="/rbac-sample", tags=["rbac-sample"])


@sample_router.get("/write", dependencies=[require_permission("profile.write")])
async def sample_write() -> dict[str, bool]:
    return {"ok": True}


@sample_router.get("/suspend", dependencies=[require_permission("users.suspend")])
async def sample_suspend() -> dict[str, bool]:
    return {"ok": True}


@sample_router.get("/assign", dependencies=[require_permission("roles.assign")])
async def sample_assign() -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture
async def api(
    db_session: AsyncSession, otp_redis: Redis
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()
    app.include_router(sample_router)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://id.test", headers=UA
    ) as client:
        yield client, db_session


async def _me_user(session: AsyncSession, phone: str) -> User:
    user = await session.scalar(select(User).where(User.phone == phone))
    assert user is not None
    return user


async def test_plain_user_permission_matrix(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    await _login(http, session, phone="+919876500001")
    assert (await http.get("/rbac-sample/write")).status_code == 200
    assert (await http.get("/rbac-sample/suspend")).status_code == 403
    assert (await http.get("/rbac-sample/assign")).status_code == 403


async def test_staff_gains_suspend_next_request_without_invalidation(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """user->roles is read fresh per request: no cache to invalidate."""
    http, session = api
    await _login(http, session, phone="+919876500002")
    assert (await http.get("/rbac-sample/suspend")).status_code == 403
    user = await _me_user(session, "+919876500002")
    await assign_role(session, user.id, "staff")
    assert (await http.get("/rbac-sample/suspend")).status_code == 200
    assert (await http.get("/rbac-sample/assign")).status_code == 403  # staff still can't assign


async def test_super_admin_passes_all_three(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone="+919876500003")
    user = await _me_user(session, "+919876500003")
    await assign_role(session, user.id, "super_admin")
    for path in ("/rbac-sample/write", "/rbac-sample/suspend", "/rbac-sample/assign"):
        assert (await http.get(path)).status_code == 200


async def test_matrix_is_cached_until_reset(
    db_session: AsyncSession, rbac_matrix: RbacMatrix
) -> None:
    """role->permissions rides the TTL cache; mutating grants requires
    reset_permission_cache() (the invalidation hook role-matrix tooling must call)."""
    assert "profile.write" in await permissions_for_roles(db_session, ("user",))
    # 0051 made the catalog read-only for app_rt, so the revoke goes through
    # the owner and is committed - db_session reads it on its next statement
    await rbac_matrix.revoke("user", "profile.write")
    assert "profile.write" in await permissions_for_roles(db_session, ("user",))  # stale by design
    reset_permission_cache()
    assert "profile.write" not in await permissions_for_roles(db_session, ("user",))


async def test_unknown_role_grants_nothing(db_session: AsyncSession) -> None:
    assert await permissions_for_roles(db_session, ("ghost_role",)) == frozenset()
