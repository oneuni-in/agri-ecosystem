"""HTTP middleware: 301s for recorded slug changes.

Runs after routing: only a GET/HEAD that would otherwise 404 costs a
redirect lookup, so the happy path never touches the database.

That lookup is rate limited, because it is the one database query in the
service that a route dependency cannot cover. SecureRouter attaches the
limiter per route, so a path matching NO route skips it - which left an
unmatched GET costing a query per request, on a path the caller invents, with
nothing counting it.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.types import ASGIApp

from shared.db import get_sessionmaker
from shared.security import client_ip, rate_limiter
from shared.slugs import find_redirect

Lookup = Callable[[str], Awaitable[str | None]]

# Its own key space, so a flood of 404s cannot exhaust the budget a caller
# needs for real routes (or the reverse).
_MISS_KEY = "slugmiss:{ip}"


async def _db_lookup(path: str) -> str | None:
    async with get_sessionmaker()() as session:
        return await find_redirect(session, path)


class SlugRedirectMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, lookup: Lookup = _db_lookup) -> None:
        super().__init__(app)
        self._lookup = lookup

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if response.status_code == 404 and request.method in ("GET", "HEAD"):
            if not await rate_limiter.hit(_MISS_KEY.format(ip=client_ip(request))):
                # over budget: the 301 is a courtesy for someone following a
                # stale link, and it is the right thing to drop under flood
                return response
            target = await self._lookup(request.url.path)
            if target is not None:
                return RedirectResponse(target, status_code=301)
        return response
