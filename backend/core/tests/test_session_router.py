"""D09.A/C at the HTTP layer: login (new + returning), cookie discipline,
fixation, suspended deny, logout, logout-everywhere in one request."""

from collections.abc import AsyncIterator

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import SessionRefresh, SessionWeb, User
from modules.identity.otp_drivers import MockDriver
from modules.identity.otp_service import issue_otp, verify_otp
from modules.identity.session_limits import SESSION_COOKIE_NAME
from shared.db import get_session

PHONE = "+919876530001"
UA = {"user-agent": "pytest-browser", "sec-ch-ua-platform": '"Windows"'}


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


async def _otp_proof(session: AsyncSession, phone: str = PHONE) -> str:
    # clear throttle ladders between logins - these tests exercise sessions,
    # not the D07 resend cooldown (proofs are consumed immediately, so a
    # flush of the dedicated test redis DB loses nothing that matters)
    from shared.cache import get_redis

    await get_redis().flushdb()
    await issue_otp(session, phone=phone, purpose="login", ip=None, device_fingerprint=None)
    code = MockDriver.last_code(phone)
    assert code is not None
    return await verify_otp(session, phone=phone, purpose="login", code=code, ip=None)


async def _login(
    http: httpx.AsyncClient, session: AsyncSession, phone: str = PHONE
) -> httpx.Response:
    proof = await _otp_proof(session, phone)
    return await http.post("/auth/login", json={"otp_proof": proof})


async def test_new_user_login_sets_cookie_and_creates_account(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    response = await _login(http, session)
    assert response.status_code == 200
    body = response.json()
    assert body["is_new_user"] is True
    assert body["agri_id"].startswith("AG-")
    assert body["handle_is_fallback"] is True
    cookie = response.headers["set-cookie"]
    assert SESSION_COOKIE_NAME in cookie
    lowered = cookie.lower()
    assert "httponly" in lowered and "secure" in lowered and "samesite=lax" in lowered
    assert "domain=" not in lowered  # host-only: id.agri.in and nowhere else
    user = (await session.scalars(select(User))).one()
    assert user.phone_verified_at is not None


async def test_returning_login_and_session_fixation(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    first = await _login(http, session)
    second = await _login(http, session)
    assert second.json()["is_new_user"] is False
    # fixation: every login mints a brand-new sid
    sid1 = first.cookies[SESSION_COOKIE_NAME]
    sid2 = second.cookies[SESSION_COOKIE_NAME]
    assert sid1 != sid2
    assert len((await session.scalars(select(User))).all()) == 1


async def test_login_rejects_bad_or_reused_proof(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    assert (await http.post("/auth/login", json={"otp_proof": "junk"})).status_code == 400
    proof = await _otp_proof(session)
    assert (await http.post("/auth/login", json={"otp_proof": proof})).status_code == 200
    reuse = await http.post("/auth/login", json={"otp_proof": proof})  # GETDEL burned it
    assert reuse.status_code == 400


async def test_suspended_user_cannot_login_or_use_session(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session)
    user = (await session.scalars(select(User))).one()
    user.status = "suspended"
    await session.flush()
    assert (await http.get("/auth/me")).status_code == 401  # instant deny mid-session
    relogin = await _login(http, session)
    assert relogin.status_code == 403


async def test_me_requires_session_and_returns_public_shape(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    assert (await http.get("/auth/me")).status_code == 401
    login = await _login(http, session)
    me = await http.get("/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["agri_id"] == login.json()["agri_id"]
    assert "id" not in body and "user_id" not in body and "phone" not in body


async def test_logout_kills_session_and_device_refresh(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session)
    response = await http.post("/auth/logout")
    assert response.status_code == 200
    assert (await http.get("/auth/me")).status_code == 401
    row = (await session.scalars(select(SessionWeb))).one()
    assert row.revoked_at is not None


async def test_logout_everywhere_one_request_cycle(
    api: tuple[httpx.AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-negotiable: ALL sessions + refresh families die in one request."""

    # back-channel notification (D10.D) is best-effort but must not make real
    # network calls in tests - stub it out here, dedicated coverage lives in
    # test_backchannel_logout.py.
    async def _no_notify(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr("modules.identity.session_router.notify_logout_everywhere", _no_notify)
    http, session = api
    await _login(http, session)  # device A's session (older, no longer in jar)
    await _login(http, session)  # device B's session (in the client jar now)

    response = await http.post("/auth/logout-everywhere")
    assert response.status_code == 200

    web_rows = (await session.scalars(select(SessionWeb))).all()
    refresh_rows = (await session.scalars(select(SessionRefresh))).all()
    assert len(web_rows) == 2 and all(r.revoked_at is not None for r in web_rows)
    assert all(r.revoked_at is not None for r in refresh_rows)
    assert (await http.get("/auth/me")).status_code == 401
