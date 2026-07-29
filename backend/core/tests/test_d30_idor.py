"""D30.A section 3: cross-tenant IDOR sweep.

Every business_id-scoped route is an IDOR candidate: the id is caller-supplied
and names someone else's property. One case per route, all driven by the same
attacker principal against a business they do not own.

A 200 here is a High. A 500 is at least a Medium - it means the handler got
past the ownership check and into logic it should never have reached.
"""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import service as directory_service
from modules.identity.service import create_user
from shared.db import get_session
from shared.security import register_principal_resolver


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


@pytest.fixture
async def two_owners(
    db_session: AsyncSession,
) -> AsyncIterator[tuple[httpx.AsyncClient, uuid.UUID, dict[str, str]]]:
    """(client, victim_business_id, attacker_headers).

    Both users hold the ordinary "user" role - this is a horizontal privilege
    check, not a vertical one. The attacker owns a business of their own, so a
    refusal cannot be explained away by "they are not a vendor at all".
    """
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

    victim = await create_user(db_session, "+919000000801")
    attacker = await create_user(db_session, "+919000000802")
    victim_business = await directory_service.create_business(
        db_session,
        owner_user_id=victim.id,
        name="D30 Victim Dairy",
        type_="vendor",
        primary_pincode="641001",
        description={"en": "victim"},
    )
    await directory_service.create_business(
        db_session,
        owner_user_id=attacker.id,
        name="D30 Attacker Dairy",
        type_="vendor",
        primary_pincode="641002",
        description={"en": "attacker"},
    )
    await db_session.flush()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client, victim_business.id, {"x-test-user": str(attacker.id), "x-test-roles": "user"}


@pytest.fixture
async def two_owners_owner_view(
    db_session: AsyncSession,
) -> AsyncIterator[tuple[httpx.AsyncClient, uuid.UUID, dict[str, str]]]:
    """Same world as two_owners, but the headers belong to the OWNER."""
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

    owner = await create_user(db_session, "+919000000803")
    business = await directory_service.create_business(
        db_session,
        owner_user_id=owner.id,
        name="D30 Control Dairy",
        type_="vendor",
        primary_pincode="641003",
        description={"en": "control"},
    )
    await db_session.flush()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client, business.id, {"x-test-user": str(owner.id), "x-test-roles": "user"}


# (method, path template, json body or None)
ROUTES = [
    ("PATCH", "/directory/businesses/{bid}", {"description": {"en": "pwned"}}),
    ("POST", "/directory/businesses/{bid}/rename", {"new_slug": "pwned-dairy"}),
    (
        "POST",
        "/directory/businesses/{bid}/branches",
        {
            "address": "1 Attacker Road",
            "state": "Tamil Nadu",
            "district": "Coimbatore",
            "pincode": "641001",
        },
    ),
    ("PUT", "/directory/businesses/{bid}/coverage", {"pincodes": ["641002"]}),
    (
        "PUT",
        "/directory/businesses/{bid}/categories",
        {"category_ids": ["00000000-0000-7000-8000-000000000001"]},
    ),
    ("PUT", "/directory/businesses/{bid}/tier-selection", {"tier": "premium"}),
    ("GET", "/directory/businesses/{bid}/tier-selection", None),
    ("GET", "/directory/businesses/{bid}/analytics", None),
    (
        "POST",
        "/catalog/businesses/{bid}/products",
        {"vertical_slug": "milk", "name": "Pwned Milk", "specs": {}, "price_display": "1"},
    ),
    ("GET", "/leads/inbox?business_id={bid}", None),
    ("GET", "/leads/inbox/stats?business_id={bid}", None),
]


@pytest.mark.parametrize("method,path,body", ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
async def test_cross_tenant_access_is_refused(
    two_owners: tuple[httpx.AsyncClient, uuid.UUID, dict[str, str]],
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    client, victim_business_id, attacker = two_owners

    response = await client.request(
        method,
        path.format(bid=victim_business_id),
        json=body,
        headers=attacker,
    )

    assert response.status_code in (403, 404), (
        f"{method} {path} leaked cross-tenant: {response.status_code} {response.text[:300]}"
    )


@pytest.mark.parametrize("method,path,body", ROUTES, ids=[f"owner {m} {p}" for m, p, _ in ROUTES])
async def test_the_owner_is_not_refused(
    two_owners_owner_view: tuple[httpx.AsyncClient, uuid.UUID, dict[str, str]],
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    """Positive control for the sweep above.

    Without this the refusal test proves nothing: a mistyped path also answers
    404, so every case could "pass" while testing routes that do not exist. The
    owner must NOT get 403/404 on the same URL - any other status (200, 201,
    409, 422) means the route is real and the refusal above was an authz
    decision rather than a routing accident.
    """
    client, victim_business_id, owner = two_owners_owner_view

    response = await client.request(
        method,
        path.format(bid=victim_business_id),
        json=body,
        headers=owner,
    )

    assert response.status_code not in (403, 404), (
        f"{method} {path} refused the OWNER ({response.status_code}) - the "
        f"cross-tenant case above is therefore not evidence of anything: "
        f"{response.text[:300]}"
    )
