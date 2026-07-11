"""D09.A: /authorize consults the id.agri.in session - mints a code when
present, parks the request at /login?next= when absent."""

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import User
from shared.db import get_session
from tests.test_oauth_flow import REDIRECT, _authorize_params, _exchange, _pkce
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


async def test_authorize_without_session_redirects_to_login_resume(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    _, challenge = _pkce()
    response = await http.get("/authorize", params=_authorize_params(challenge))
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("/login?next=")  # RELATIVE - never an absolute foreign URL
    resumed = unquote(location.removeprefix("/login?next="))
    assert resumed.startswith("/authorize?")
    assert "state=state-xyz" in resumed


async def test_authorize_with_session_mints_code(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    verifier, challenge = _pkce()
    login = await _login(http, session)  # sets agri_sid; login assigns the "user" role
    assert login.status_code == 200

    response = await http.get("/authorize", params=_authorize_params(challenge))
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(REDIRECT + "?")
    query = parse_qs(urlsplit(location).query)
    assert query["state"] == ["state-xyz"]
    code = query["code"][0]

    exchange = await _exchange(http, code, verifier)
    assert exchange.status_code == 200
    assert exchange.json()["refresh_token"]


async def test_authorize_with_session_still_validates_pkce_and_client(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    _, challenge = _pkce()
    await _login(http, session)
    # missing challenge: error redirect, NO code minted despite the session
    bad = await http.get("/authorize", params=_authorize_params(challenge, code_challenge=""))
    query = parse_qs(urlsplit(bad.headers["location"]).query)
    assert query["error"] == ["invalid_request"] and "code" not in query
    # unknown client: 400 JSON, no redirect, session irrelevant
    evil = await http.get("/authorize", params=_authorize_params(challenge, client_id="evil-app"))
    assert evil.status_code == 400 and "location" not in evil.headers


async def test_authorize_suspended_session_parks_at_login(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    _, challenge = _pkce()
    await _login(http, session)
    user = (await session.scalars(select(User))).one()
    user.status = "suspended"
    await session.flush()
    response = await http.get("/authorize", params=_authorize_params(challenge))
    assert response.headers["location"].startswith("/login?next=")  # instant deny


async def test_authorize_prompt_none_without_session_returns_login_required(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    _, challenge = _pkce()
    params = _authorize_params(challenge) | {"prompt": "none"}
    response = await http.get("/authorize", params=params)
    assert response.status_code == 302
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == REDIRECT
    query = parse_qs(location.query)
    assert query["error"] == ["login_required"]
    assert query["state"] == ["state-xyz"]


async def test_authorize_prompt_none_with_session_mints_code(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session)  # sets agri_sid; login assigns the "user" role
    _, challenge = _pkce()
    params = _authorize_params(challenge) | {"prompt": "none"}
    response = await http.get("/authorize", params=params)
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert "code" in query
