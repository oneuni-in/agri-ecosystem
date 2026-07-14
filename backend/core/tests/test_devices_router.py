"""D09.D backend: device list/label/revoke + handle picker + language."""

from collections.abc import AsyncIterator

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import Profile, User
from shared.audit import AuditEntry
from shared.db import get_session
from tests.test_session_router import UA, _login


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


async def test_devices_list_marks_current(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    await _login(http, session)
    response = await http.get("/auth/devices")
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    device = body["items"][0]
    assert device["current"] is True and device["kind"] == "web"
    assert set(device) >= {"device_id", "kind", "label", "current", "created_at"}


async def test_device_label_and_revoke_other(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session)
    first_id = (await http.get("/auth/devices")).json()["items"][0]["device_id"]
    await _login(http, session)  # second session; cookie jar now holds session 2

    labelled = await http.post(
        "/auth/devices/label", json={"device_id": first_id, "kind": "web", "label": "Old laptop"}
    )
    assert labelled.status_code == 200
    items = (await http.get("/auth/devices")).json()["items"]
    assert {"Old laptop"} <= {item["label"] for item in items}

    revoked = await http.post("/auth/devices/revoke", json={"device_id": first_id, "kind": "web"})
    assert revoked.status_code == 200
    items = (await http.get("/auth/devices")).json()["items"]
    assert len(items) == 1 and items[0]["current"] is True  # only session 2 left


async def test_revoke_rejects_foreign_and_garbage_ids(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session)
    response = await http.post(
        "/auth/devices/revoke", json={"device_id": "not-a-uuid", "kind": "web"}
    )
    assert response.status_code == 404
    response = await http.post(
        "/auth/devices/revoke",
        json={"device_id": "01890000-0000-7000-8000-000000000000", "kind": "web"},
    )
    assert response.status_code == 404


async def test_handle_check_suggest_and_set(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    await _login(http, session)
    old_handle = (await session.scalars(select(User))).one().agri_id

    check = await http.get("/auth/handle/check", params={"h": "good_farmer"})
    assert check.json() == {"ok": True, "code": None}
    invalid = await http.get("/auth/handle/check", params={"h": "ab"})
    assert invalid.json()["code"] == "invalid_format"
    reserved = await http.get("/auth/handle/check", params={"h": "admin"})
    assert reserved.json()["code"] == "reserved"

    suggest = await http.get("/auth/handle/suggest")
    suggestions = suggest.json()["suggestions"]
    assert len(suggestions) == 3 and all("_" in s for s in suggestions)

    taken = await http.post("/auth/handle", json={"handle": "good_farmer"})
    assert taken.status_code == 200
    assert taken.json()["agri_id"] == "good_farmer"
    user = (await session.scalars(select(User))).one()
    assert user.agri_id == "good_farmer" and user.agri_id_changed_once is True

    audit_rows = (
        await session.scalars(
            select(AuditEntry).where(AuditEntry.action == "identity.handle_changed")
        )
    ).all()
    assert len(audit_rows) == 1
    assert audit_rows[0].meta == {"old": old_handle, "new": "good_farmer"}

    again = await http.post("/auth/handle", json={"handle": "second_pick"})
    assert again.status_code == 409  # one free change ever
    assert again.json()["detail"] == "already_changed"


async def test_handle_conflict_is_409_taken(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    await _login(http, session, phone="+919876540001")
    assert (await http.post("/auth/handle", json={"handle": "unique_name"})).status_code == 200
    await _login(http, session, phone="+919876540002")
    response = await http.post("/auth/handle", json={"handle": "unique_name"})
    assert response.status_code == 409
    assert response.json()["detail"] == "taken"


async def test_language_upserts_profile(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    await _login(http, session)
    assert (await http.post("/auth/language", json={"language": "ta"})).status_code == 200
    profile = (await session.scalars(select(Profile))).one()
    assert profile.language == "ta"
    assert (await http.get("/auth/me")).json()["language"] == "ta"
    assert (await http.post("/auth/language", json={"language": "xx"})).status_code == 422
