"""U3 PERMISSION SWEEP + catalog contract.

U2 proved EXCLUSION (vendor B cannot reach vendor A). Admin legitimately
crosses those boundaries, so U3 proves ACCOUNTABILITY: every admin surface is
rejected AT THE API for anyone below its required role — not merely hidden in
the UI. This is the automated spec A2's successor passes extend; a new gated
endpoint that isn't listed here is not done.

The five actor contexts the spec names: (i) signed-out visitor, (ii) consumer,
(iii) business owner, (iv) staff, (v) admin. Expected: 401 signed-out (auth
fires first), 403 for consumer/owner (below the required role), 200 for
staff/admin on the read surfaces this pass adds.
"""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared.authz import PERMISSION_CATALOG, require_permission, roles_for
from shared.db import get_session
from shared.security import register_principal_resolver


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(roles: str | None) -> dict[str, str]:
    """Header set for one actor. None → signed-out (no principal resolves)."""
    if roles is None:
        return {}
    return {"x-test-user": str(uuid.uuid4()), "x-test-roles": roles}


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        if not header:
            return None
        roles = tuple((request.headers.get("x-test-roles") or "user").split(","))
        return _Principal(uuid.UUID(header), roles)

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client


# (method, path) for every read surface U3 adds, each gated by the shared
# permission guard. staff/super_admin may read; everyone below is rejected.
_READ_SURFACES = [
    ("GET", "/admin/ops/pincode-tiers"),
    ("GET", "/admin/directory/businesses"),
    ("GET", "/admin/ads/performance?date_from=2026-08-01&date_to=2026-08-13"),
    ("GET", "/admin/payments/ledger"),
    ("GET", "/admin/payments/events"),
]

# actor label → (roles header value | None, expected status on a read surface)
_ACTORS = {
    "signed_out": (None, 401),
    "consumer": ("user", 403),
    "business_owner": ("business_owner", 403),
    "staff": ("staff", 200),
    "admin": ("super_admin", 200),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", _READ_SURFACES)
@pytest.mark.parametrize("actor", list(_ACTORS))
async def test_read_surface_rejects_below_role(
    api: httpx.AsyncClient, method: str, path: str, actor: str
) -> None:
    roles, expected = _ACTORS[actor]
    response = await api.request(method, path, headers=_as(roles))
    assert response.status_code == expected, (
        f"{actor} on {path}: expected {expected}, got {response.status_code}"
    )
    # rejections are AT THE API, and generic — the catalog layout is not a
    # surface. 403s carry missing_permission (the shared guard), never a leak.
    if expected == 403:
        assert response.json()["detail"] == "missing_permission"


# --- the catalog contract (RBAC v2 forward-compat vocabulary) --------------


def test_catalog_registers_the_spec_vocabulary() -> None:
    """The permission keys the spec names must exist as a registered catalog,
    not scattered string literals — RBAC v2 becomes a grant matrix over THIS
    vocabulary, so the keys are the stable contract."""
    for key in (
        "reviews.moderate",
        "products.approve",
        "brands.verify",
        "reports.handle",
        "ads.creatives.approve",
        "ads.slots.config",
        "coins.adjust",
        "audit.read",
    ):
        assert key in PERMISSION_CATALOG, f"{key} missing from PERMISSION_CATALOG"


def test_coins_writes_are_super_admin_only() -> None:
    """D13 invariant preserved through the catalog: staff cannot adjust coins."""
    assert roles_for("coins.adjust") == frozenset({"super_admin"})
    assert roles_for("coins.rules.manage") == frozenset({"super_admin"})
    assert "staff" in roles_for("moderation.read")  # but staff can moderate


def test_unregistered_key_fails_loudly() -> None:
    """A typo in a route's permission key must fail at import/decoration, never
    resolve to silently-open."""
    with pytest.raises(KeyError):
        require_permission("not.a.real.permission")
