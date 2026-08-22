"""D09.D backend: device list/label/revoke + handle picker + language."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import Profile, SessionRefresh, User
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
    # two DIFFERENT devices: re-logging in on the same one now supersedes its
    # own previous session (session_service.create_web_session), so a same-UA
    # second login would leave nothing "other" to label or revoke.
    phone = {"user-agent": "Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile Safari/537.36"}
    await _login(http, session, headers=phone)
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


# --- ID-U1 P8: a row has to say WHICH SITE, WHAT DEVICE, WHERE, WHEN --------


async def test_device_row_carries_a_readable_device_description(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    # a real browser UA, sent on the request that mints the session
    chrome = {
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "sec-ch-ua-platform": '"Windows"',
    }
    await _login(http, session, headers=chrome)
    row = (await http.get("/auth/devices", headers=chrome)).json()["items"][0]
    assert row["device_kind"] == "Windows - Chrome"
    # geoip is state-level and only active with a provisioned mmdb, so `place`
    # is a nullable field the UI simply omits - it must still be PRESENT in
    # the payload, or the client cannot tell "unknown" from "not implemented".
    assert "place" in row


async def test_unrecognisable_agent_is_null_not_a_guess(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    odd = {"user-agent": "curl/8.4.0", "sec-ch-ua-platform": '"Unknown"'}
    await _login(http, session, headers=odd)
    row = (await http.get("/auth/devices", headers=odd)).json()["items"][0]
    # None, so the screen says "Unknown device" rather than naming the wrong
    # thing. Rows created before migration 0054 read the same way, and there
    # is nothing to backfill them from - the raw UA was never stored.
    assert row["device_kind"] is None


async def test_rows_from_one_device_share_a_group_key(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """The web session and every app session minted from one browser carry the
    same key, so the screen can show that laptop once instead of once per app."""
    from modules.identity.oauth_service import get_client
    from modules.identity.refresh_service import issue_refresh_token
    from modules.identity.session_service import device_fingerprint

    http, session = api
    await _login(http, session)
    user = (await session.scalars(select(User))).one()
    client = await get_client(session, "web-agri")
    assert client is not None
    # the same browser that logged in above now completes an SSO handshake
    await issue_refresh_token(
        session,
        user_id=user.id,
        client=client,
        fingerprint=device_fingerprint(UA["user-agent"]),
        ip=None,
    )

    rows = (await http.get("/auth/devices")).json()["items"]
    assert {row["kind"] for row in rows} == {"web", "web-agri"}
    assert len({row["device_group"] for row in rows}) == 1


async def test_app_row_dates_from_the_family_root_not_the_latest_rotation(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Rotation must not make a months-old app session look brand new.

    The list used to report the CURRENT rotation row's created_at, so every
    silent token refresh reset the "when" the screen shows - a session from
    weeks ago kept re-appearing as a device that signed in minutes ago.
    """
    from modules.identity.oauth_service import get_client
    from modules.identity.refresh_service import issue_refresh_token, rotate_refresh_token

    http, session = api
    await _login(http, session)
    user = (await session.scalars(select(User))).one()
    client = await get_client(session, "web-agri")
    assert client is not None

    issued = await issue_refresh_token(
        session, user_id=user.id, client=client, fingerprint="fp-x", ip=None
    )
    root = await session.scalar(select(SessionRefresh).where(SessionRefresh.id == issued.family_id))
    assert root is not None
    # server_default now() is transaction-constant, so age the root explicitly:
    # without a real gap the rotation descendant would share its timestamp and
    # the assertion below would pass even against the broken query.
    root_created = datetime.now(UTC) - timedelta(days=30)
    root.created_at = root_created
    await session.flush()

    await rotate_refresh_token(session, token=issued.token, client=client, fingerprint="fp-x")

    rows = (await http.get("/auth/devices")).json()["items"]
    app_row = next(row for row in rows if row["kind"] == "web-agri")
    assert datetime.fromisoformat(app_row["created_at"]) == root_created


async def test_the_raw_user_agent_is_never_stored(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    from modules.identity.models import SessionWeb

    http, session = api
    chrome = {
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "sec-ch-ua-platform": '"Windows"',
    }
    await _login(http, session, headers=chrome)
    row = await session.scalar(select(SessionWeb).order_by(SessionWeb.id.desc()).limit(1))
    assert row is not None
    # the whole point of deriving a description instead of adding a
    # user_agent column: the high-entropy string must not be at rest.
    assert row.device_kind == "Windows - Chrome"
    assert chrome["user-agent"] not in (row.device_kind or "")
    assert not hasattr(row, "user_agent")
