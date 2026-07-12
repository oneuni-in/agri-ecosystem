"""D10.D: logout-everywhere tells every registered BFF, best-effort."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from joserfc import jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.backchannel import (
    BACKCHANNEL_PATH,
    LOGOUT_EVENT,
    backchannel_uris,
    build_logout_token,
    notify_logout_everywhere,
)
from modules.identity.models import OAuthClient, SessionWeb
from modules.identity.oauth_keys import get_key_set
from modules.identity.otp_drivers import MockDriver
from modules.identity.otp_service import issue_otp, verify_otp
from settings import get_settings
from shared.db import get_session

PHONE = "+919876540099"
UA = {"user-agent": "pytest-browser", "sec-ch-ua-platform": '"Windows"'}


def _client(uris: list[str]) -> OAuthClient:
    return OAuthClient(client_id="web-milk", redirect_uris=uris)


def test_backchannel_uris_derive_and_dedupe_origins() -> None:
    client = _client(
        [
            "http://localhost:3000/api/auth/callback",
            "http://localhost:3000/other/callback",
        ]
    )
    assert backchannel_uris(client) == [f"http://localhost:3000{BACKCHANNEL_PATH}"]


def test_logout_token_verifies_against_jwks() -> None:
    client = _client(["http://localhost:3000/api/auth/callback"])
    user_id = uuid.uuid4()
    token = build_logout_token(client, user_id)
    decoded = jwt.decode(token, get_key_set())
    assert decoded.claims["iss"] == get_settings().oauth_issuer
    assert decoded.claims["aud"] == "web-milk"
    assert decoded.claims["sub"] == str(user_id)
    assert LOGOUT_EVENT in decoded.claims["events"]


async def test_notify_posts_to_every_client_and_survives_failures(
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert "logout_token" in request.content.decode()
        if "3001" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200)

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    with caplog.at_level("WARNING"):
        await notify_logout_everywhere(db_session, uuid.uuid4(), client_factory=factory)
    # one POST per seeded client origin (4 in dev/test), failures non-fatal
    assert len(seen) == 4
    assert all(url.endswith(BACKCHANNEL_PATH) for url in seen)
    # a non-2xx response must be visible in the logs, same as a raised exception
    assert "backchannel.logout.delivery_failed" in caplog.text


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


async def test_logout_everywhere_endpoint_survives_pregather_notify_failure(
    api: tuple[httpx.AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the CRITICAL finding: a failure BEFORE asyncio.gather
    (token minting, key lookup...) must not escape logout_everywhere and roll
    back revoke_everything. This must FAIL against the pre-fix code (the
    RuntimeError propagates out of the endpoint)."""

    def _boom(*args: object, **kwargs: object) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr("modules.identity.backchannel.build_logout_token", _boom)
    http, session = api
    await _login(http, session)

    response = await http.post("/auth/logout-everywhere")
    assert response.status_code == 200

    rows = (await session.scalars(select(SessionWeb))).all()
    assert rows and all(row.revoked_at is not None for row in rows)


async def test_logout_everywhere_endpoint_survives_real_delivery_failures(
    api: tuple[httpx.AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """End-to-end through the REAL notify function: one BFF 500s, one is
    unreachable (ConnectError). Both are per-POST failures already shielded
    by asyncio.gather(return_exceptions=True), so revocation must commit and
    the endpoint must still return 200."""
    original_post = httpx.AsyncClient.post

    async def patched_post(
        self: httpx.AsyncClient, url: httpx.URL | str, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        text = str(url)
        if BACKCHANNEL_PATH not in text:
            return await original_post(self, url, *args, **kwargs)
        request = httpx.Request("POST", text)
        if "3001" in text:
            return httpx.Response(500, request=request)
        if "3004" in text:
            raise httpx.ConnectError("simulated unreachable BFF", request=request)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", patched_post)
    http, session = api
    await _login(http, session)

    with caplog.at_level("WARNING"):
        response = await http.post("/auth/logout-everywhere")
    assert response.status_code == 200

    rows = (await session.scalars(select(SessionWeb))).all()
    assert rows and all(row.revoked_at is not None for row in rows)
    assert "backchannel.logout.delivery_failed" in caplog.text
