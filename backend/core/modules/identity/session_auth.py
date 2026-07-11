"""The registered principal resolver + handler-side dependency (D09.C).

require_auth rides the request-scoped get_session dependency, so the resolver
shares the endpoint's session/transaction - the last_seen_at touch commits
(or rolls back) with the endpoint's own writes.
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.session_limits import SESSION_COOKIE_NAME
from modules.identity.session_service import WebPrincipal, resolve_web_session


async def resolve_principal(request: Request, session: AsyncSession) -> WebPrincipal | None:
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if not sid:
        return None
    return await resolve_web_session(session, sid)


def current_principal(request: Request) -> WebPrincipal:
    principal = getattr(request.state, "principal", None)
    assert isinstance(principal, WebPrincipal), "route must be private (require_auth ran)"
    return principal


PrincipalDep = Annotated[WebPrincipal, Depends(current_principal)]
