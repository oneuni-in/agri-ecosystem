"""D10.A: /oauth/revoke - a BFF retires its own refresh family on app logout.
Always 200 (RFC 7009 §2.2): the response never reveals whether the token existed."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared.db import get_session
from tests.test_oauth_flow import _exchange, _mint_code, _pkce

CLIENT_ID = "web-agri"
OTHER_CLIENT_ID = "web-milk"


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


async def _login_and_exchange(http: httpx.AsyncClient, session: AsyncSession) -> str:
    verifier, challenge = _pkce()
    code, _ = await _mint_code(session, challenge)
    response = await _exchange(http, code, verifier)  # httpx sends its own UA consistently
    assert response.status_code == 200
    token: str = response.json()["refresh_token"]
    return token


async def test_revoke_kills_the_family(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    refresh_token = await _login_and_exchange(http, session)

    response = await http.post(
        "/oauth/revoke", data={"client_id": CLIENT_ID, "token": refresh_token}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # the revoked family must now refuse to rotate
    rotate = await http.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        },
    )
    assert rotate.status_code == 400
    assert rotate.json()["error"] == "invalid_grant"


async def test_revoke_unknown_token_still_200(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    response = await http.post(
        "/oauth/revoke", data={"client_id": CLIENT_ID, "token": "no-such-token"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_revoke_unknown_client_still_200(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    response = await http.post("/oauth/revoke", data={"client_id": "evil-app", "token": "whatever"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_revoke_missing_params_still_200(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    response = await http.post("/oauth/revoke", data={"client_id": CLIENT_ID})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_revoke_foreign_client_is_noop(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    refresh_token = await _login_and_exchange(http, session)
    response = await http.post(
        "/oauth/revoke", data={"client_id": OTHER_CLIENT_ID, "token": refresh_token}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    # family survives: rotation from the RIGHT client still works
    rotate = await http.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        },
    )
    assert rotate.status_code == 200
