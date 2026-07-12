"""OIDC-style back-channel logout (D10.D).

logout-everywhere revokes everything server-side, then tells every registered
BFF so app sessions die NOW instead of at the ~15-minute access-token horizon
(the silent re-auth safety net). Delivery is best-effort: a dead client app
must never block or fail the user's logout. Nothing here logs bodies; the
only logged value on failure is the destination URI."""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from joserfc import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import OAuthClient
from modules.identity.oauth_keys import get_signing_key
from settings import get_settings
from shared.telemetry import get_logger

logger = get_logger(__name__)

LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
BACKCHANNEL_PATH = "/api/auth/backchannel-logout"
NOTIFY_TIMEOUT_SECONDS = 3.0

ClientFactory = Callable[..., httpx.AsyncClient]


def backchannel_uris(client: OAuthClient) -> list[str]:
    """One per distinct redirect-URI origin. Derived, not stored: the path is
    fixed by @agri/auth-client and origins are already reviewed migration
    data (0009) - no new registry surface to keep in sync."""
    origins: list[str] = []
    for uri in client.redirect_uris:
        parts = urlsplit(uri)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in origins:
            origins.append(origin)
    return [f"{origin}{BACKCHANNEL_PATH}" for origin in origins]


def build_logout_token(client: OAuthClient, user_id: uuid.UUID) -> str:
    key = get_signing_key()
    now = int(datetime.now(UTC).timestamp())
    claims = {
        "iss": get_settings().oauth_issuer,
        "aud": client.client_id,
        "sub": str(user_id),  # server-to-server only; browsers never see this
        "iat": now,
        "exp": now + 120,
        "jti": str(uuid.uuid4()),
        "events": {LOGOUT_EVENT: {}},
    }
    return jwt.encode({"alg": "RS256", "kid": key.kid, "typ": "JWT"}, claims, key)


async def notify_logout_everywhere(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    client_factory: ClientFactory = httpx.AsyncClient,
) -> None:
    clients = (await session.scalars(select(OAuthClient))).all()
    posts = [
        (uri, build_logout_token(client, user_id))
        for client in clients
        for uri in backchannel_uris(client)
    ]
    if not posts:
        return
    async with client_factory(timeout=NOTIFY_TIMEOUT_SECONDS) as http:
        results = await asyncio.gather(
            *(http.post(uri, data={"logout_token": token}) for uri, token in posts),
            return_exceptions=True,
        )
    for (uri, _), result in zip(posts, results, strict=True):
        if isinstance(result, BaseException) or result.status_code >= 400:
            logger.warning("backchannel.logout.delivery_failed uri=%s", uri)
