"""D11: D08 access tokens as a first-class principal for BFF backend calls."""

import time
import uuid
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from joserfc import jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import User
from modules.identity.oauth_keys import get_signing_key
from settings import get_settings
from shared.db import get_session
from tests.test_session_router import UA, _login

PHONE = "+919876511111"


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


def _mint(user_id: uuid.UUID, *, expires_in: int = 900, issuer: str | None = None) -> str:
    key = get_signing_key()
    now = int(time.time())
    claims = {
        "iss": issuer or get_settings().oauth_issuer,
        "sub": str(user_id),
        "aud": "web-admin",
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode({"alg": "RS256", "kid": key.kid, "typ": "JWT"}, claims, key)


async def _fresh_user(http: httpx.AsyncClient, session: AsyncSession) -> User:
    await _login(http, session, phone=PHONE)
    http.cookies.clear()  # bearer-only from here: prove the cookie isn't doing the work
    user = await session.scalar(select(User).where(User.phone == PHONE))
    assert user is not None
    return user


async def test_valid_bearer_reaches_private_route(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    user = await _fresh_user(http, session)
    response = await http.get("/auth/me", headers={"authorization": f"Bearer {_mint(user.id)}"})
    assert response.status_code == 200
    assert response.json()["agri_id"] == user.agri_id


def _expired(user_id: uuid.UUID) -> str:
    return _mint(user_id, expires_in=-60)


def _wrong_issuer(user_id: uuid.UUID) -> str:
    return _mint(user_id, issuer="https://evil.example")


def _garbage(user_id: uuid.UUID) -> str:
    return "not-a-jwt"


def _unknown_subject(user_id: uuid.UUID) -> str:
    return _mint(uuid.uuid4())


@pytest.mark.parametrize(
    "token_builder",
    [_expired, _wrong_issuer, _garbage, _unknown_subject],
)
async def test_bad_bearer_is_401(
    api: tuple[httpx.AsyncClient, AsyncSession], token_builder: Callable[[uuid.UUID], str]
) -> None:
    http, session = api
    user = await _fresh_user(http, session)
    response = await http.get(
        "/auth/me", headers={"authorization": f"Bearer {token_builder(user.id)}"}
    )
    assert response.status_code == 401


async def test_suspended_user_bearer_denied_within_one_request(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """The token stays cryptographically valid; the DB status check kills it."""
    http, session = api
    user = await _fresh_user(http, session)
    token = _mint(user.id)
    ok = await http.get("/auth/me", headers={"authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    user.status = "suspended"
    await session.flush()
    denied = await http.get("/auth/me", headers={"authorization": f"Bearer {token}"})
    assert denied.status_code == 401


async def test_bearer_logout_is_a_clean_noop(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """No web session to revoke; must not 500 (session_id is None)."""
    http, session = api
    user = await _fresh_user(http, session)
    response = await http.post(
        "/auth/logout", headers={"authorization": f"Bearer {_mint(user.id)}"}
    )
    assert response.status_code == 200
