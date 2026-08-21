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

Session integration (D09): a fully valid /authorize consults the id.agri.in
session cookie - present and active mints a one-time code and 302s to the
client; absent (or suspended) 302s to the RELATIVE /login resume whose next
value is this request's own path+query (never an open-redirect surface).

Silent SSO probe (D10.B): when the caller sets prompt=none, an absent (or
suspended) session never reaches the login UI - it 302s straight back to the
already-validated redirect_uri with error=login_required&state=..., so a BFF
can check for a session without a visible redirect.
"""

from typing import Annotated
from urllib.parse import quote

from authlib.oauth2.rfc6749 import InvalidRequestError, OAuth2Error
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, RedirectResponse, Response

from modules.identity.device_kind import describe_device
from modules.identity.oauth_keys import get_jwks
from modules.identity.oauth_server import (
    AgriAuthorizationServer,
    ClientWrapper,
    RequestContext,
    build_oauth2_request,
)
from modules.identity.oauth_service import (
    consume_authorization_code,
    create_authorization_code,
    get_client,
    load_token_subject,
)
from modules.identity.refresh_service import (
    RefreshInvalidError,
    issue_refresh_token,
    revoke_by_token,
    revoke_family,
    rotate_refresh_token,
)
from modules.identity.session_limits import SESSION_COOKIE_NAME
from modules.identity.session_service import device_fingerprint, resolve_web_session
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
    """Validate, then consult the id.agri.in session (D09).

    Order matters: authlib validates client_id + exact redirect_uri before any
    redirecting error can exist, then PKCE (S256 required), then our
    state-required rule. Only a fully valid request gets to see the session:
    - session present and active -> mint a one-time code, 302 to the client.
    - no session (or suspended), prompt=none -> 302 to the redirect_uri with
      error=login_required&state=... (D10.B silent SSO probe: no login UI).
    - no session (or suspended), otherwise  -> 302 to the RELATIVE login
      resume; the next value is this request's own path+query, so it can
      never point anywhere but back here."""
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
    except OAuth2Error as error:
        return server.handle_response(*error(None))

    sid = request.cookies.get(SESSION_COOKIE_NAME)
    principal = await resolve_web_session(session, sid) if sid else None
    if principal is None:
        if params.get("prompt") == "none":
            # Silent SSO probe (D10.B): the BFF asked "is anyone home?" -
            # answer through the already-validated redirect_uri, never by
            # parking the user at the login UI.
            return RedirectResponse(
                f"{grant.redirect_uri}?error=login_required"
                f"&state={quote(params['state'], safe='')}",
                status_code=302,
            )
        resume = f"{request.url.path}?{request.url.query}"
        return RedirectResponse(f"/login?next={quote(resume, safe='')}", status_code=302)
    assert ctx.client is not None  # get_consent_grant validated it
    code = await create_authorization_code(
        session,
        user_id=principal.user_id,
        client=ctx.client.row,
        redirect_uri=grant.redirect_uri,
        code_challenge=params["code_challenge"],
    )
    return RedirectResponse(
        f"{grant.redirect_uri}?code={quote(code, safe='')}&state={quote(params['state'], safe='')}",
        status_code=302,
    )


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
    grant_type = params.get("grant_type")
    fingerprint = device_fingerprint(
        request.headers.get("user-agent"), request.headers.get("sec-ch-ua-platform")
    )
    code = params.get("code")
    if ctx.client is not None and grant_type == "authorization_code" and code:
        ctx.code = await consume_authorization_code(session, code=code, client=ctx.client.row)
        if ctx.code is not None:
            ctx.subject = await load_token_subject(session, ctx.code.user_id)
        if ctx.code is not None and ctx.subject is not None:
            # D09: every successful code exchange starts a refresh family,
            # bound to the exchanging device (D10's BFF forwards the browser
            # UA so the binding is the user's browser, not the BFF host)
            issued = await issue_refresh_token(
                session,
                user_id=ctx.code.user_id,
                client=ctx.client.row,
                fingerprint=fingerprint,
                ip=request.client.host if request.client else None,
                # D10's BFF forwards the browser's UA, so this describes the
                # user's device rather than the BFF host.
                device_kind=describe_device(
                    request.headers.get("user-agent"),
                    request.headers.get("sec-ch-ua-platform"),
                ),
            )
            ctx.new_refresh_token = issued.token
            ctx.issued_family_id = issued.family_id
    elif ctx.client is not None and grant_type == "refresh_token" and params.get("refresh_token"):
        try:
            # burn-on-attempt: the old token is retired even if authlib
            # rejects the request afterwards (mirrors D08 code burning)
            rotation = await rotate_refresh_token(
                session,
                token=params["refresh_token"],
                client=ctx.client.row,
                fingerprint=fingerprint,
            )
            ctx.rotation = rotation
            ctx.subject = rotation.subject
            ctx.new_refresh_token = rotation.token
            ctx.issued_family_id = rotation.family_id
        except RefreshInvalidError:
            pass  # ctx.rotation stays None -> authlib answers invalid_grant
    await session.commit()
    server = AgriAuthorizationServer(ctx)
    try:
        oauth2_request = build_oauth2_request("POST", str(request.url), params, datalist)
    except OAuth2Error as error:
        return server.handle_response(*error(None))
    response: Response = server.create_token_response(oauth2_request)
    if response.status_code != 200 and ctx.issued_family_id is not None:
        # a refresh credential whose plaintext never reached a client must
        # not linger as a phantom device in the manager
        await revoke_family(session, ctx.issued_family_id)
        await session.commit()
    return response


@oauth_router.post("/oauth/revoke", public=True)
async def revoke(request: Request, session: SessionDep) -> JSONResponse:
    """App-logout back-channel (D10.A): a BFF retires its own refresh family.
    Always 200 (RFC 7009 §2.2) - never reveal whether the token existed."""
    form = await request.form()
    client_id = form.get("client_id")
    token = form.get("token")
    if isinstance(client_id, str) and isinstance(token, str) and client_id and token:
        row = await get_client(session, client_id)
        if row is not None:
            await revoke_by_token(session, token=token, client=row)
            await session.commit()
    return JSONResponse({"status": "ok"})


@oauth_router.get("/.well-known/jwks.json", public=True)
async def jwks() -> JSONResponse:
    """Public signing keys (active + rotation overlap). Downstream verifiers
    may cache briefly; the rotation runbook budgets for this max-age."""
    return JSONResponse(get_jwks(), headers={"Cache-Control": "public, max-age=300"})
