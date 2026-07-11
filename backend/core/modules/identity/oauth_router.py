"""OAuth2 endpoints (D08.A/C/E): /authorize, /token, /.well-known/jwks.json.

All three are public by design and declared in backend/core/public_routes.txt;
SecureRouter still rate-limits them. Per module rules nothing here logs query
strings or bodies - authorize requests carry state and code_challenge, token
requests carry codes and verifiers.

Error discipline (spec E - no open redirect): an error may travel as a 302
only after authlib validated client_id AND redirect_uri against the seeded
registry; every earlier failure is a 400 JSON with no Location header.
authlib's error classes encode exactly that split - errors raised before
redirect validation carry no redirect_uri, so handle_response renders JSON.

Until D09 lands there is no id.agri.in session, so a fully valid /authorize
request always ends in error=login_required redirected to the registered
redirect_uri with the caller's state - D09 replaces that final raise with the
real session check and login resume.
"""

from typing import Annotated

from authlib.oauth2.rfc6749 import InvalidRequestError, OAuth2Error
from authlib.oidc.core.errors import LoginRequiredError
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response

from modules.identity.oauth_keys import get_jwks
from modules.identity.oauth_server import (
    AgriAuthorizationServer,
    ClientWrapper,
    RequestContext,
    build_oauth2_request,
)
from modules.identity.oauth_service import (
    consume_authorization_code,
    get_client,
    load_token_subject,
)
from shared.db import get_session
from shared.security import SecureRouter

oauth_router = SecureRouter(tags=["oauth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _client_context(session: AsyncSession, client_id: str | None) -> RequestContext:
    ctx = RequestContext()
    if client_id:
        row = await get_client(session, client_id)
        if row is not None:
            ctx.client = ClientWrapper(row)
    return ctx


@oauth_router.get("/authorize", public=True)
async def authorize(request: Request, session: SessionDep) -> Response:
    """Validate an authorization request; with no session yet (D09), park it.

    Order matters: authlib validates client_id + exact redirect_uri before any
    redirecting error can exist, then PKCE (S256 required), then our
    state-required rule, and only a request that passed everything earns the
    login_required redirect."""
    params = {key: request.query_params[key] for key in request.query_params}
    datalist = {key: request.query_params.getlist(key) for key in request.query_params}
    ctx = await _client_context(session, params.get("client_id"))
    server = AgriAuthorizationServer(ctx)
    try:
        oauth2_request = build_oauth2_request("GET", str(request.url), params, datalist)
        grant = server.get_consent_grant(request=oauth2_request, end_user=None)
        if not params.get("state"):
            raise InvalidRequestError(
                "Missing 'state' in request.", redirect_uri=grant.redirect_uri
            )
        raise LoginRequiredError(redirect_uri=grant.redirect_uri, state=params["state"])
    except OAuth2Error as error:
        return server.handle_response(*error(None))


@oauth_router.post("/token", public=True)
async def token(request: Request, session: SessionDep) -> Response:
    """Exchange a one-time code (+ PKCE verifier) for an RS256 access token.

    The code is consumed atomically BEFORE authlib judges the request, and the
    burn is committed BEFORE the response is built - a rejected exchange must
    never roll back consumed_at (D07's commit-before-400 lesson), and a racing
    duplicate can never win."""
    form = await request.form()
    params = {key: value for key, value in form.items() if isinstance(value, str)}
    datalist = {
        key: [value for value in form.getlist(key) if isinstance(value, str)] for key in form
    }
    ctx = await _client_context(session, params.get("client_id"))
    code = params.get("code")
    if ctx.client is not None and code:
        ctx.code = await consume_authorization_code(session, code=code, client=ctx.client.row)
        if ctx.code is not None:
            ctx.subject = await load_token_subject(session, ctx.code.user_id)
    await session.commit()
    server = AgriAuthorizationServer(ctx)
    try:
        oauth2_request = build_oauth2_request("POST", str(request.url), params, datalist)
    except OAuth2Error as error:
        return server.handle_response(*error(None))
    response: Response = server.create_token_response(oauth2_request)
    return response


@oauth_router.get("/.well-known/jwks.json", public=True)
async def jwks() -> JSONResponse:
    """Public signing keys (active + rotation overlap). Downstream verifiers
    may cache briefly; the rotation runbook budgets for this max-age."""
    return JSONResponse(get_jwks(), headers={"Cache-Control": "public, max-age=300"})
