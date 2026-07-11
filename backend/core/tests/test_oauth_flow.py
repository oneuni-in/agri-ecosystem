"""D08.F endpoint suite on the real app: the full code+PKCE flow and every
rejection the spec names. Base URL is https because authlib (correctly)
refuses OAuth over insecure transport.

D09 note: until sessions exist, /authorize answers every VALID request with a
login_required error redirect, so the happy path mints its code through
oauth_service.create_authorization_code - the exact call D09's post-login step
will make - and exchanges it at the real /token endpoint.
"""

import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from joserfc import jwt
from joserfc.jwk import KeySet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import OAuthCode, User
from modules.identity.oauth_limits import ACCESS_TOKEN_TTL_SECONDS
from modules.identity.oauth_service import create_authorization_code, get_client
from modules.identity.service import assign_role, create_user
from settings import get_settings
from shared.db import get_session

REDIRECT = "http://localhost:3002/api/auth/callback"
MILK_REDIRECT = "http://localhost:3000/api/auth/callback"


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


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    return verifier, create_s256_code_challenge(verifier)


def _authorize_params(challenge: str, **overrides: str) -> dict[str, str]:
    params = {
        "response_type": "code",
        "client_id": "web-agri",
        "redirect_uri": REDIRECT,
        "state": "state-xyz",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    params.update(overrides)
    return {key: value for key, value in params.items() if value}


async def _mint_code(
    session: AsyncSession,
    challenge: str,
    *,
    client_id: str = "web-agri",
    redirect_uri: str = REDIRECT,
    roles: tuple[str, ...] = ("user",),
) -> tuple[str, User]:
    """The D09 post-login step: a logged-in user's valid request earns a code."""
    user = await create_user(session, "+919876543210")
    for role in roles:
        await assign_role(session, user.id, role)
    client = await get_client(session, client_id)
    assert client is not None
    code = await create_authorization_code(
        session,
        user_id=user.id,
        client=client,
        redirect_uri=redirect_uri,
        code_challenge=challenge,
    )
    return code, user


async def _exchange(
    http: httpx.AsyncClient, code: str, verifier: str, **overrides: str
) -> httpx.Response:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "client_id": "web-agri",
        "code_verifier": verifier,
    }
    data.update(overrides)
    return await http.post("/token", data={k: v for k, v in data.items() if v})


def _location_query(response: httpx.Response) -> dict[str, list[str]]:
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(REDIRECT + "?"), "errors may redirect only to the registered URI"
    return parse_qs(urlsplit(location).query)


# --- the full flow -----------------------------------------------------------


async def test_full_code_flow_with_pkce(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    verifier, challenge = _pkce()

    # step 1: a valid /authorize parks at login_required until D09 sessions
    authorize = await http.get("/authorize", params=_authorize_params(challenge))
    query = _location_query(authorize)
    assert query["error"] == ["login_required"]
    assert query["state"] == ["state-xyz"]
    assert "code" not in query

    # step 2 (D09 stand-in): post-login, the same request mints a code
    code, user = await _mint_code(session, challenge)

    # step 3: exchange at the real endpoint
    response = await _exchange(http, code, verifier)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == ACCESS_TOKEN_TTL_SECONDS
    assert "refresh_token" not in body  # D09, not sooner

    # step 4: the token verifies against the served JWKS and carries D08.D claims
    jwks = (await http.get("/.well-known/jwks.json")).json()
    decoded = jwt.decode(body["access_token"], KeySet.import_key_set(jwks))
    assert decoded.header["alg"] == "RS256"
    assert decoded.header["kid"] in {key["kid"] for key in jwks["keys"]}
    claims = decoded.claims
    assert claims["iss"] == get_settings().oauth_issuer
    assert claims["sub"] == str(user.id)  # internal UUID: services only, never browsers
    assert claims["aud"] == "web-agri"
    assert claims["agri_id"] == user.agri_id
    assert claims["roles"] == ["user"]
    assert claims["exp"] - claims["iat"] == ACCESS_TOKEN_TTL_SECONDS


# --- token endpoint rejections ------------------------------------------------


async def test_wrong_verifier_rejected_and_code_burned(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    verifier, challenge = _pkce()
    code, _ = await _mint_code(session, challenge)

    wrong = await _exchange(http, code, secrets.token_urlsafe(48))
    assert wrong.status_code == 400
    assert wrong.json()["error"] == "invalid_grant"

    # the failed attempt consumed the code: even the right verifier is dead now
    retry = await _exchange(http, code, verifier)
    assert retry.status_code == 400
    assert retry.json()["error"] == "invalid_grant"


async def test_code_reuse_rejected(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    verifier, challenge = _pkce()
    code, _ = await _mint_code(session, challenge)

    assert (await _exchange(http, code, verifier)).status_code == 200
    reuse = await _exchange(http, code, verifier)
    assert reuse.status_code == 400
    assert reuse.json()["error"] == "invalid_grant"


async def test_expired_code_rejected(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    verifier, challenge = _pkce()
    code, _ = await _mint_code(session, challenge)
    row = (await session.scalars(select(OAuthCode))).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()

    response = await _exchange(http, code, verifier)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


async def test_token_redirect_uri_mismatch_rejected(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    verifier, challenge = _pkce()
    code, _ = await _mint_code(session, challenge)

    response = await _exchange(http, code, verifier, redirect_uri=REDIRECT + "/other")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


async def test_foreign_client_cannot_exchange(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    verifier, challenge = _pkce()
    code, _ = await _mint_code(session, challenge)

    foreign = await _exchange(
        http, code, verifier, client_id="web-milk", redirect_uri=MILK_REDIRECT
    )
    assert foreign.status_code == 400
    assert foreign.json()["error"] == "invalid_grant"

    # the foreign attempt must not burn the rightful client's code
    rightful = await _exchange(http, code, verifier)
    assert rightful.status_code == 200


async def test_unknown_client_id_rejected_at_token(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    verifier, challenge = _pkce()
    code, _ = await _mint_code(session, challenge)

    response = await _exchange(http, code, verifier, client_id="evil-app")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client"


async def test_suspended_user_gets_no_token(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    verifier, challenge = _pkce()
    code, user = await _mint_code(session, challenge)
    user.status = "suspended"
    await session.flush()

    response = await _exchange(http, code, verifier)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


# --- authorize endpoint --------------------------------------------------------


async def test_authorize_unknown_client_gets_json_never_redirect(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    _, challenge = _pkce()
    response = await http.get(
        "/authorize", params=_authorize_params(challenge, client_id="evil-app")
    )
    assert response.status_code == 400
    assert "location" not in response.headers
    assert response.json()["error"] == "invalid_client"


async def test_authorize_unregistered_redirect_gets_json_never_redirect(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    _, challenge = _pkce()
    for attacker_uri in (
        "https://evil.example/callback",
        REDIRECT + "/../evil",  # no substring/prefix matching
        REDIRECT.upper(),  # exact means exact
    ):
        response = await http.get(
            "/authorize", params=_authorize_params(challenge, redirect_uri=attacker_uri)
        )
        assert response.status_code == 400
        assert "location" not in response.headers
        assert response.json()["error"] == "invalid_request"


async def test_authorize_missing_state_rejected(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    _, challenge = _pkce()
    response = await http.get("/authorize", params=_authorize_params(challenge, state=""))
    query = _location_query(response)  # client+redirect were valid: safe redirect
    assert query["error"] == ["invalid_request"]
    assert "code" not in query


async def test_authorize_requires_s256_challenge(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    _, challenge = _pkce()
    for params in (
        _authorize_params(challenge, code_challenge=""),  # PKCE missing entirely
        _authorize_params(challenge, code_challenge_method="plain"),  # no plain fallback
        _authorize_params(challenge, code_challenge_method=""),  # method omitted
    ):
        response = await http.get("/authorize", params=params)
        query = _location_query(response)
        assert query["error"] == ["invalid_request"]
        assert query["state"] == ["state-xyz"]
        assert "code" not in query


async def test_authorize_rejects_non_code_response_types(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    _, challenge = _pkce()
    response = await http.get(
        "/authorize", params=_authorize_params(challenge, response_type="token")
    )
    query = _location_query(response)
    assert query["error"] == ["unsupported_response_type"]


# --- jwks ----------------------------------------------------------------------


async def test_jwks_serves_valid_public_keys(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    response = await http.get("/.well-known/jwks.json")
    assert response.status_code == 200
    keys = response.json()["keys"]
    assert len(keys) >= 1
    for key in keys:
        assert key["kty"] == "RSA"
        assert key["alg"] == "RS256"
        assert key["use"] == "sig"
        assert key["kid"]
        assert not {"d", "p", "q", "dp", "dq", "qi"} & key.keys()
