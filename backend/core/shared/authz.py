"""The admin-console permission catalog and its ONE shared guard (U3).

Forward-compatibility seam for the deferred RBAC v2 (four tiers, nine
permission domains) — built now so the later work is a grant matrix over an
EXISTING vocabulary, not a forty-route refactor:

- Permission keys live in ONE catalog (`PERMISSION_CATALOG`), never as scattered
  string literals. Every admin management/read surface names its permission
  here; RBAC v2 re-points the catalog at a grants table without touching a
  single route.
- `require_permission(key)` is the single guard. Today its body maps the key to
  the roles that satisfy it and checks `request.state.principal.roles` — a
  role check wearing a permission's name. When `require_rank_over()` /
  grant-matrix resolution lands, ONLY this function's body changes.
- It is a ROUTER-LEVEL dependency (`dependencies=[require_permission(...)]`) so
  a new route cannot silently ship without a gate — the threat SecureRouter
  already guards for auth, extended to authorization.

Scope guard rails (U3): NO `rank` column, NO grants table, NO tiers here. This
is vocabulary + one checkpoint, nothing more. It lives in `shared` (not a
module) because import-linter forbids the admin modules from importing identity
and forbids them importing each other — the catalog is the one place all of
them, plus a future identity-side resolver, can share.
"""

import uuid
from typing import Any

from fastapi import Depends, HTTPException, Request

# Role names as seeded in migration 0008. Kept as constants so the catalog
# reads as intent, not magic strings.
STAFF = "staff"
SUPER_ADMIN = "super_admin"

_STAFF_UP: frozenset[str] = frozenset({STAFF, SUPER_ADMIN})
_SUPER_ONLY: frozenset[str] = frozenset({SUPER_ADMIN})

# The admin-console vocabulary. Value = the roles that satisfy the permission
# TODAY (a static role map; RBAC v2 replaces the resolution, not the keys).
# Grouped by surface. Every key an admin endpoint gates on must appear here —
# `require_permission` refuses an unregistered key at decoration time.
PERMISSION_CATALOG: dict[str, frozenset[str]] = {
    # moderation queues (ops console)
    "moderation.read": _STAFF_UP,
    "reviews.moderate": _STAFF_UP,
    "products.approve": _STAFF_UP,
    "brands.verify": _STAFF_UP,
    "claims.handle": _STAFF_UP,
    "reports.handle": _STAFF_UP,
    # ads
    "ads.creatives.approve": _STAFF_UP,
    "ads.campaigns.manage": _STAFF_UP,
    "ads.slots.config": _STAFF_UP,
    "ads.ratecard.publish": _STAFF_UP,
    "ads.performance.read": _STAFF_UP,
    # coins (writes are super-admin only, per D13)
    "coins.read": _STAFF_UP,
    "coins.adjust": _SUPER_ONLY,
    "coins.rules.manage": _SUPER_ONLY,
    "coins.abuse.handle": _STAFF_UP,
    # directory + enforcement
    "directory.read": _STAFF_UP,
    "directory.enforce": _STAFF_UP,
    # geo tiers (read-only browse; override stays on its existing route)
    "tiers.read": _STAFF_UP,
    # payments ledger (DISPLAY ONLY — no write permission is defined on purpose)
    "payments.read": _STAFF_UP,
    # users
    "users.read": _STAFF_UP,
    "users.manage": _STAFF_UP,
    # operational flags (super-admin only — a flag is a production lever)
    "flags.manage": _SUPER_ONLY,
    # audit reader (Group C)
    "audit.read": _STAFF_UP,
    # content engine (E6, A-U3). `content.publish` IS the human gate: the
    # RSS worker and the CMS both leave items `pending`, and this is the
    # only permission that can move one forward. Split from `content.write`
    # deliberately — drafting and approving are different acts, and RBAC v2
    # needs them separable to give an editor one without the other.
    "content.read": _STAFF_UP,
    "content.write": _STAFF_UP,
    "content.publish": _STAFF_UP,
}


def roles_for(permission: str) -> frozenset[str]:
    """The roles that satisfy `permission` today. Raises on an unregistered
    key so a typo fails loudly at import, not silently open at runtime."""
    try:
        return PERMISSION_CATALOG[permission]
    except KeyError:  # pragma: no cover - developer error, surfaced immediately
        raise KeyError(
            f"permission {permission!r} is not in PERMISSION_CATALOG (shared/authz.py)"
        ) from None


def resolve_actor(request: Request) -> uuid.UUID:
    """The acting admin's user_id, for the audit row. Call inside a handler
    whose route already carries `require_permission(...)` — the gate has run,
    so this only extracts (and fails closed if, defensively, no principal)."""
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=403, detail="missing_permission")
    user_id = principal.user_id
    return user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))


def require_permission(permission: str) -> Any:
    """THE shared admin guard, as a router-level dependency.

    Usage (router level so no endpoint can be forgotten):

        @router.get("/thing", dependencies=[require_permission("thing.read")])

    Today: 403 unless the resolved principal holds a role that grants
    `permission` in the catalog. Multi-role principals get the union. The
    detail is generic (`missing_permission`) — the catalog layout is not an
    API surface. Return type is `Any` for the same reason identity.rbac's
    require_permission uses it: fastapi's `Depends(...)` overloads don't narrow.
    """
    allowed = roles_for(permission)  # validated at decoration time

    async def dependency(request: Request) -> None:
        principal = getattr(request.state, "principal", None)
        roles: tuple[str, ...] = getattr(principal, "roles", ()) if principal else ()
        if not any(role in allowed for role in roles):
            raise HTTPException(status_code=403, detail="missing_permission")

    return Depends(dependency)
