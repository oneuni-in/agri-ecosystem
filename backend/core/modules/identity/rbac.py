"""require_permission (D11.C): roles -> permissions through a cached matrix.

Freshness contract (the design decision, spelled out):
- user -> roles is NEVER cached. The principal resolver (D09/session_auth)
  loads roles from the DB on every request, so assigning or removing a role
  takes effect on the target's next request with zero invalidation machinery -
  and suspension already denies at resolve time (one request cycle,
  non-negotiable 3).
- role -> permissions changes only via migration today (there is no
  role-matrix editing endpoint in D11), so it rides a short in-process TTL
  cache (the flags.py idiom). Any future endpoint that mutates
  role_permissions MUST call reset_permission_cache() in the same request.

Usage on a SecureRouter route (require_auth has already populated
request.state.principal by the time route-level dependencies after it run):

    @router.post("/thing", dependencies=[require_permission("thing.write")])
"""

import time
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Permission, Role, RolePermission
from modules.identity.session_auth import current_principal
from shared.db import get_session

PERMISSION_CACHE_TTL_SECONDS = 30.0

_cache: tuple[float, dict[str, frozenset[str]]] | None = None


def reset_permission_cache() -> None:
    global _cache
    _cache = None


async def role_permission_matrix(session: AsyncSession) -> dict[str, frozenset[str]]:
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < PERMISSION_CACHE_TTL_SECONDS:
        return _cache[1]
    rows = await session.execute(
        select(Role.name, Permission.name)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
    )
    matrix: dict[str, set[str]] = {}
    for role_name, permission_name in rows:
        matrix.setdefault(role_name, set()).add(permission_name)
    frozen = {name: frozenset(perms) for name, perms in matrix.items()}
    _cache = (now, frozen)
    return frozen


async def permissions_for_roles(session: AsyncSession, roles: tuple[str, ...]) -> frozenset[str]:
    matrix = await role_permission_matrix(session)
    granted: set[str] = set()
    for role in roles:
        granted |= matrix.get(role, frozenset())
    return frozenset(granted)


def require_permission(permission: str) -> Any:
    """403 unless the resolved principal's roles grant `permission`.

    Multi-role users get the UNION of their roles' grants. The detail stays
    generic - the matrix layout is not an API surface.

    Return type is `Any` rather than `fastapi.params.Depends`: mypy flags
    `Depends(dependency)` itself as returning `Any` (fastapi's overloads
    don't narrow it here), so annotating the return as `params.Depends`
    just trades one no-any-return error for a dishonest annotation.
    """

    async def dependency(
        request: Request, session: Annotated[AsyncSession, Depends(get_session)]
    ) -> None:
        principal = current_principal(request)
        granted = await permissions_for_roles(session, principal.roles)
        if permission not in granted:
            raise HTTPException(status_code=403, detail="missing_permission")

    return Depends(dependency)
