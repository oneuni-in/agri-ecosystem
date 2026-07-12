"""The registered principal resolver + handler-side dependency (D09.C, D11).

require_auth rides the request-scoped get_session dependency, so the resolver
shares the endpoint's session/transaction - the last_seen_at touch commits
(or rolls back) with the endpoint's own writes.

Two credential shapes resolve here, cookie first:
- agri_sid session cookie (browsers on id.agri.in) -> resolve_web_session
- Authorization: Bearer <D08 access token> (BFF server-side calls, D11) ->
  resolve_bearer_token. Roles and status come FRESH from the DB, never from
  token claims: a suspension or role change beats the token's remaining
  lifetime (non-negotiable: one request cycle). aud is deliberately not
  pinned - this API is the resource server for every first-party client.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Request
from joserfc import jwt
from joserfc.errors import JoseError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.oauth_keys import get_key_set
from modules.identity.oauth_service import load_token_subject
from modules.identity.session_limits import SESSION_COOKIE_NAME
from modules.identity.session_service import WebPrincipal, resolve_web_session
from settings import get_settings


async def resolve_principal(request: Request, session: AsyncSession) -> WebPrincipal | None:
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if sid:
        return await resolve_web_session(session, sid)
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return await resolve_bearer_token(session, token.strip())
    return None


async def resolve_bearer_token(session: AsyncSession, token: str) -> WebPrincipal | None:
    """None for malformed, mis-signed, expired, wrong-issuer, unknown-subject,
    and suspended - indistinguishable to callers, all 401."""
    try:
        decoded = jwt.decode(token, get_key_set(), algorithms=["RS256"])
        jwt.JWTClaimsRegistry(
            iss={"essential": True, "value": get_settings().oauth_issuer},
            exp={"essential": True},
            sub={"essential": True},
        ).validate(decoded.claims)
        user_id = uuid.UUID(str(decoded.claims["sub"]))
    except (JoseError, ValueError):
        return None
    subject = await load_token_subject(session, user_id)
    if subject is None:  # suspended or gone: instant deny
        return None
    return WebPrincipal(
        user_id=subject.user_id,
        agri_id=subject.agri_id,
        roles=subject.roles,
        session_id=None,
        fingerprint=None,
    )


def current_principal(request: Request) -> WebPrincipal:
    principal = getattr(request.state, "principal", None)
    assert isinstance(principal, WebPrincipal), "route must be private (require_auth ran)"
    return principal


PrincipalDep = Annotated[WebPrincipal, Depends(current_principal)]
