"""D11.D: admin surface. Non-negotiables pinned here: full phone never in any
admin response, suspension kills access within one request cycle, super_admin
assignment requires super_admin."""

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import cast

import httpx
import pytest
import uuid6
from joserfc import jwt
from redis.asyncio import Redis
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import Permission, Role, RolePermission, User
from modules.identity.oauth_keys import get_signing_key
from modules.identity.rbac import reset_permission_cache
from modules.identity.service import assign_role
from settings import get_settings
from shared.db import get_session
from tests.test_session_router import UA, _login, _stream_entries

ADMIN_PHONE = "+919876533333"
TARGET_PHONE = "+919876544444"


@pytest.fixture
async def api(
    db_session: AsyncSession, otp_redis: Redis
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://id.test", headers=UA
    ) as client:
        yield client, db_session


async def _user(session: AsyncSession, phone: str) -> User:
    user = await session.scalar(select(User).where(User.phone == phone))
    assert user is not None
    return user


async def _login_admin(
    http: httpx.AsyncClient, session: AsyncSession, *, role: str = "staff"
) -> User:
    await _login(http, session, phone=ADMIN_PHONE)
    admin = await _user(session, ADMIN_PHONE)
    await assign_role(session, admin.id, role)
    return admin


async def _make_target(http: httpx.AsyncClient, session: AsyncSession) -> User:
    """Login as target (creates the account + a live session cookie snapshot),
    then restore no-cookie state for the admin login that follows."""
    await _login(http, session, phone=TARGET_PHONE)
    http.cookies.clear()
    return await _user(session, TARGET_PHONE)


async def test_search_last4_and_full_phone_never_rendered(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    target = await _make_target(http, session)
    await _login_admin(http, session)
    response = await http.get("/admin/users", params={"q": TARGET_PHONE[-4:]})
    assert response.status_code == 200
    body = response.json()
    found = [item for item in body["items"] if item["agri_id"] == target.agri_id]
    assert len(found) == 1 and found[0]["phone_last4"] == TARGET_PHONE[-4:]
    # THE non-negotiable: the full number appears nowhere in the payload.
    assert TARGET_PHONE not in response.text and TARGET_PHONE.lstrip("+") not in response.text

    detail = await http.get(f"/admin/users/{target.agri_id}")
    assert detail.status_code == 200
    assert TARGET_PHONE not in detail.text and TARGET_PHONE.lstrip("+") not in detail.text


async def test_search_by_agri_id_prefix(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    target = await _make_target(http, session)
    await _login_admin(http, session)
    response = await http.get("/admin/users", params={"q": target.agri_id[:5]})
    assert any(item["agri_id"] == target.agri_id for item in response.json()["items"])


async def test_permission_denied_paths_per_role(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    target = await _make_target(http, session)
    # plain user: nothing on /admin works
    await _login(http, session, phone=ADMIN_PHONE)
    assert (await http.get("/admin/users", params={"q": "1234"})).status_code == 403
    assert (await http.post(f"/admin/users/{target.agri_id}/suspend")).status_code == 403
    assert (
        await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    ).status_code == 403
    # staff: read + suspend yes, roles.assign no
    admin = await _user(session, ADMIN_PHONE)
    await assign_role(session, admin.id, "staff")
    assert (await http.get("/admin/users", params={"q": "1234"})).status_code == 200
    assert (
        await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    ).status_code == 403
    # super_admin: everything
    await assign_role(session, admin.id, "super_admin")
    assert (
        await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    ).status_code == 200


async def test_role_assign_remove_and_unknowns(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    target = await _make_target(http, session)
    await _login_admin(http, session, role="super_admin")
    assigned = await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    assert assigned.status_code == 200 and "farmer" in assigned.json()["roles"]
    duplicate = await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    assert duplicate.status_code == 409
    unknown = await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "wizard"})
    assert unknown.status_code == 404
    removed = await http.request("DELETE", f"/admin/users/{target.agri_id}/roles/farmer")
    assert removed.status_code == 200 and "farmer" not in removed.json()["roles"]
    not_assigned = await http.request("DELETE", f"/admin/users/{target.agri_id}/roles/farmer")
    assert not_assigned.status_code == 404
    ghost = await http.post("/admin/users/does_not_exist/roles", json={"role": "farmer"})
    assert ghost.status_code == 404


async def test_add_role_publishes_role_changed_event(
    api: tuple[httpx.AsyncClient, AsyncSession], otp_redis: Redis
) -> None:
    """add_role's best-effort publish (commit-then-announce) must land exactly
    one identity.role_changed entry on the "identity" stream, carrying the
    assigned role and the target's agri_id - never their phone."""
    http, session = api
    target = await _make_target(http, session)
    await _login_admin(http, session, role="super_admin")
    assigned = await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    assert assigned.status_code == 200 and "farmer" in assigned.json()["roles"]

    raw = cast(list[tuple[str, dict[str, str]]], await otp_redis.xrange("identity", "-", "+"))
    entries = _stream_entries(raw)
    role_changed = [e for e in entries if e["type"] == "identity.role_changed"]
    assert len(role_changed) == 1
    event = role_changed[0]
    assert event["agri_id"] == target.agri_id
    assert event["vars"] == {"role": "farmer"}
    assert TARGET_PHONE not in json.dumps(event)


async def test_super_admin_assignment_requires_super_admin(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Privilege-escalation guard. Staff normally lacks roles.assign entirely,
    so grant it temporarily - the guard must STILL refuse super_admin."""
    http, session = api
    target = await _make_target(http, session)
    await _login_admin(http, session, role="staff")
    role_id = await session.scalar(select(Role.id).where(Role.name == "staff"))
    perm_id = await session.scalar(select(Permission.id).where(Permission.name == "roles.assign"))
    await session.execute(
        insert(RolePermission).values(id=uuid6.uuid7(), role_id=role_id, permission_id=perm_id)
    )
    reset_permission_cache()
    escalate = await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "super_admin"})
    assert escalate.status_code == 403
    assert escalate.json()["detail"] == "super_admin_required"
    # and removing super_admin from someone is equally guarded
    await assign_role(session, target.id, "super_admin")
    demote = await http.request("DELETE", f"/admin/users/{target.agri_id}/roles/super_admin")
    assert demote.status_code == 403


def _bearer(user_id: uuid.UUID) -> dict[str, str]:
    key = get_signing_key()
    now = int(time.time())
    claims = {
        "iss": get_settings().oauth_issuer,
        "sub": str(user_id),
        "aud": "web-admin",
        "iat": now,
        "exp": now + 900,
    }
    token = jwt.encode({"alg": "RS256", "kid": key.kid, "typ": "JWT"}, claims, key)
    return {"authorization": f"Bearer {token}"}


async def test_suspension_kills_all_access_and_reactivate_restores_login(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    # the target gets their OWN client so their live cookie jar survives the
    # admin's login on the shared client (httpx forbids mixing per-request
    # cookies with a client jar)
    transport = http._transport  # same ASGI app
    async with (
        httpx.AsyncClient(
            transport=transport, base_url="https://id.test", headers=UA
        ) as target_http,
        # resolve_principal is cookie-first (session_auth.py): reusing `http`
        # for the bearer checks would authenticate as the admin via its own
        # still-live cookie and never touch the bearer path at all, so the
        # bearer-only assertions need a client with NO cookie jar of its own.
        httpx.AsyncClient(
            transport=transport, base_url="https://id.test", headers=UA
        ) as bearer_only,
    ):
        await _login(target_http, session, phone=TARGET_PHONE)
        target = await _user(session, TARGET_PHONE)
        target_bearer = _bearer(target.id)
        assert (await target_http.get("/auth/me")).status_code == 200  # alive pre-suspend
        await _login_admin(http, session)  # staff: has users.suspend

        suspended = await http.post(f"/admin/users/{target.agri_id}/suspend")
        assert suspended.status_code == 200
        again = await http.post(f"/admin/users/{target.agri_id}/suspend")
        assert again.status_code == 409

        # cookie dead within one request cycle
        assert (await target_http.get("/auth/me")).status_code == 401
        # bearer dead too (fresh DB status check beats token lifetime)
        assert (await bearer_only.get("/auth/me", headers=target_bearer)).status_code == 401

        reactivated = await http.post(f"/admin/users/{target.agri_id}/reactivate")
        assert reactivated.status_code == 200
        # old sessions stay revoked (revoke_everything is not undone) ...
        assert (await target_http.get("/auth/me")).status_code == 401
        # ... but the account itself works again
        assert (await bearer_only.get("/auth/me", headers=target_bearer)).status_code == 200


async def test_cannot_suspend_self_or_super_admin_as_staff(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    target = await _make_target(http, session)
    admin = await _login_admin(http, session)  # staff
    await assign_role(session, target.id, "super_admin")
    assert (await http.post(f"/admin/users/{target.agri_id}/suspend")).status_code == 403
    assert (await http.post(f"/admin/users/{admin.agri_id}/suspend")).status_code == 400


async def test_audit_rows_use_agri_ids_never_phone(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    target = await _make_target(http, session)
    await _login_admin(http, session, role="super_admin")
    assigned = await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    assert assigned.status_code == 200
    suspended = await http.post(f"/admin/users/{target.agri_id}/suspend")
    assert suspended.status_code == 200

    from shared.audit import AuditEntry

    rows = (
        await session.scalars(select(AuditEntry).where(AuditEntry.action == "admin.role_assigned"))
    ).all()
    assert len(rows) == 1
    entry = rows[0]
    assert entry.target_id == target.agri_id  # agri_id, not UUID/phone
    assert entry.actor_user_id is not None
    serialized = str(entry.meta) + str(entry.target_id)
    assert TARGET_PHONE not in serialized  # the raw phone never lands in audit
    assert entry.meta["actor"].startswith(("AG", "@")) or entry.meta["actor"]

    suspend_rows = (
        await session.scalars(select(AuditEntry).where(AuditEntry.action == "admin.user_suspended"))
    ).all()
    assert len(suspend_rows) == 1
    suspend_entry = suspend_rows[0]
    assert suspend_entry.target_id == target.agri_id
    serialized_suspend = str(suspend_entry.meta) + str(suspend_entry.target_id)
    assert TARGET_PHONE not in serialized_suspend
