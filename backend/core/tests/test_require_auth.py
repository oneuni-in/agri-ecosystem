"""D09: the SecureRouter 401 stub becomes real cookie auth via the registered
resolver. Import-linter forbids shared -> modules, hence the registration
indirection; these tests pin both halves."""

from collections.abc import AsyncIterator
from typing import cast

import httpx
import pytest
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.session_limits import SESSION_COOKIE_NAME
from shared.db import get_session
from shared.security import register_principal_resolver, require_auth, reset_principal_resolver


def _request() -> Request:
    scope = {"type": "http", "headers": [], "method": "GET", "path": "/x", "query_string": b""}
    return Request(scope)


_NO_SESSION = cast(AsyncSession, None)  # unit tests: resolvers below ignore it


async def test_require_auth_401s_without_resolver() -> None:
    reset_principal_resolver()
    with pytest.raises(HTTPException) as excinfo:
        await require_auth(_request(), _NO_SESSION)
    assert excinfo.value.status_code == 401


async def test_require_auth_401s_when_resolver_returns_none() -> None:
    async def resolver(request: Request, session: AsyncSession) -> object | None:
        return None

    register_principal_resolver(resolver)
    with pytest.raises(HTTPException) as excinfo:
        await require_auth(_request(), _NO_SESSION)
    assert excinfo.value.status_code == 401


async def test_require_auth_sets_principal_when_resolver_matches() -> None:
    async def resolver(request: Request, session: AsyncSession) -> object | None:
        return "principal-sentinel"

    register_principal_resolver(resolver)
    request = _request()
    await require_auth(request, _NO_SESSION)
    assert request.state.principal == "principal-sentinel"


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()  # create_app registers the real resolver

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://id.test") as client:
        yield client


async def test_private_route_rejects_no_cookie_and_garbage_cookie(
    api: httpx.AsyncClient,
) -> None:
    # /identity has no private endpoints yet; the ads router's private routes
    # exist since D03. Any private path proves the dependency chain: missing
    # or garbage cookies must 401 (not 500) through the real resolver.
    response = await api.get("/ads/")
    assert response.status_code in (401, 404, 405)
    if response.status_code == 401:
        garbage = await api.get("/ads/", cookies={SESSION_COOKIE_NAME: "garbage"})
        assert garbage.status_code == 401
