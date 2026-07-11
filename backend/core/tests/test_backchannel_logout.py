"""D10.D: logout-everywhere tells every registered BFF, best-effort."""

import uuid
from typing import Any

import httpx
from joserfc import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.backchannel import (
    BACKCHANNEL_PATH,
    LOGOUT_EVENT,
    backchannel_uris,
    build_logout_token,
    notify_logout_everywhere,
)
from modules.identity.models import OAuthClient
from modules.identity.oauth_keys import get_key_set
from settings import get_settings


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

    await notify_logout_everywhere(db_session, uuid.uuid4(), client_factory=factory)
    # one POST per seeded client origin (4 in dev/test), failures non-fatal
    assert len(seen) == 4
    assert all(url.endswith(BACKCHANNEL_PATH) for url in seen)
