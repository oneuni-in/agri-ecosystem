"""D09.B at the HTTP layer: grant_type=refresh_token on the real /token."""

import secrets
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import SessionRefresh
from shared.db import get_session
from tests.test_oauth_flow import _exchange, _mint_code, _pkce


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    """Real app over https (authlib rejects plain-http OAuth), test DB session."""
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://id.test") as client:
        yield client, db_session


async def _login_and_get_refresh(http: httpx.AsyncClient, session: AsyncSession) -> str:
    verifier, challenge = _pkce()
    code, _ = await _mint_code(session, challenge)
    response = await _exchange(http, code, verifier)  # httpx sends its own UA consistently
    assert response.status_code == 200
    token: str = response.json()["refresh_token"]
    return token


async def _refresh(
    http: httpx.AsyncClient, token: str, client_id: str = "web-agri"
) -> httpx.Response:
    return await http.post(
        "/token",
        data={"grant_type": "refresh_token", "refresh_token": token, "client_id": client_id},
    )


async def test_refresh_grant_rotates(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    first = await _login_and_get_refresh(http, session)
    response = await _refresh(http, first)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"]
    assert body["refresh_token"] and body["refresh_token"] != first


async def test_refresh_reuse_revokes_family_via_http(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    first = await _login_and_get_refresh(http, session)
    second = (await _refresh(http, first)).json()["refresh_token"]

    reuse = await _refresh(http, first)  # replay the rotated token
    assert reuse.status_code == 400
    assert reuse.json()["error"] == "invalid_grant"

    dead_leaf = await _refresh(http, second)  # the whole family died with it
    assert dead_leaf.status_code == 400
    rows = (await session.scalars(select(SessionRefresh))).all()
    assert rows and all(row.revoked_at is not None for row in rows)


async def test_refresh_wrong_client_rejected(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    token = await _login_and_get_refresh(http, session)
    response = await _refresh(http, token, client_id="web-milk")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


async def test_refresh_missing_token_param_rejected(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    response = await http.post(
        "/token", data={"grant_type": "refresh_token", "client_id": "web-agri"}
    )
    assert response.status_code == 400


async def test_failed_code_exchange_leaves_no_live_refresh_family(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """A refresh row minted during a PKCE-failed exchange must not survive as
    a phantom device."""
    http, session = api
    _, challenge = _pkce()
    code, _ = await _mint_code(session, challenge)
    wrong = await _exchange(http, code, secrets.token_urlsafe(48))
    assert wrong.status_code == 400
    rows = (await session.scalars(select(SessionRefresh))).all()
    assert all(row.revoked_at is not None for row in rows)
