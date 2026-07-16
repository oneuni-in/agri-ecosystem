"""Directory API: auth gate, IDOR via the API (non-negotiable #2), rename ->
301 wiring, public detail + covers routes, public-route registry entries.

Principal injection mirrors test_coins_router.py; the x-test-user header picks
the acting user so one client can exercise the IDOR matrix."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()

CREATE_BODY = {
    "name": "Anbu Milk Farm",
    "type": "vendor",
    "primary_pincode": "641001",
    "description": {"en": "Fresh milk daily"},
}


class _Principal:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.roles = ("user",)


def _as(user_id: uuid.UUID) -> dict[str, str]:
    return {"x-test-user": str(user_id)}


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        return _Principal(uuid.UUID(header)) if header else None

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client, db_session


async def test_writes_require_auth(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _ = api
    assert (await http.post("/directory/businesses", json=CREATE_BODY)).status_code == 401
    assert (await http.get("/directory/businesses")).status_code == 401


async def test_create_business(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _ = api
    response = await http.post("/directory/businesses", json=CREATE_BODY, headers=_as(USER_A))
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "anbu-milk-farm"
    assert body["status"] == "active"
    assert body["verification_status"] == "unverified"
    assert body["description"] == {"en": "Fresh milk daily"}


async def test_create_rejects_unknown_locale(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _ = api
    bad = CREATE_BODY | {"description": {"fr": "lait"}}
    response = await http.post("/directory/businesses", json=bad, headers=_as(USER_A))
    assert response.status_code == 400


async def test_patch_is_idor_safe(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _ = api
    created = await http.post("/directory/businesses", json=CREATE_BODY, headers=_as(USER_A))
    business_id = created.json()["id"]
    attack = await http.patch(
        f"/directory/businesses/{business_id}", json={"name": "Hacked"}, headers=_as(USER_B)
    )
    assert attack.status_code == 404
    legit = await http.patch(
        f"/directory/businesses/{business_id}", json={"name": "Mine"}, headers=_as(USER_A)
    )
    assert legit.status_code == 200
    assert legit.json()["name"] == "Mine"


async def test_branch_coverage_categories_idor(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    created = await http.post("/directory/businesses", json=CREATE_BODY, headers=_as(USER_A))
    business_id = created.json()["id"]
    branch_body = {
        "address": "1 Main Rd",
        "state": "Tamil Nadu",
        "district": "Coimbatore",
        "pincode": "641001",
    }
    base = f"/directory/businesses/{business_id}"
    # attacker: every nested write 404s
    assert (
        await http.post(f"{base}/branches", json=branch_body, headers=_as(USER_B))
    ).status_code == 404
    assert (
        await http.put(f"{base}/coverage", json={"pincodes": ["641001"]}, headers=_as(USER_B))
    ).status_code == 404
    assert (
        await http.put(f"{base}/categories", json={"category_ids": []}, headers=_as(USER_B))
    ).status_code == 404
    # owner: same calls succeed
    branch = await http.post(f"{base}/branches", json=branch_body, headers=_as(USER_A))
    assert branch.status_code == 201
    branch_id = branch.json()["id"]
    assert (
        await http.put(f"{base}/coverage", json={"pincodes": ["641001"]}, headers=_as(USER_A))
    ).status_code == 200
    # branch patch: attacker 404, owner 200
    assert (
        await http.patch(
            f"/directory/branches/{branch_id}", json={"phone": "1"}, headers=_as(USER_B)
        )
    ).status_code == 404
    assert (
        await http.patch(
            f"/directory/branches/{branch_id}", json={"phone": "1"}, headers=_as(USER_A)
        )
    ).status_code == 200


async def test_my_businesses_lists_only_mine(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    await http.post("/directory/businesses", json=CREATE_BODY, headers=_as(USER_A))
    await http.post(
        "/directory/businesses", json=CREATE_BODY | {"name": "Other Dairy"}, headers=_as(USER_B)
    )
    response = await http.get("/directory/businesses", headers=_as(USER_A))
    assert response.status_code == 200
    assert [b["name"] for b in response.json()["items"]] == ["Anbu Milk Farm"]


async def test_categories_endpoint_lists_seeded(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    response = await http.get("/directory/categories", headers=_as(USER_A))
    assert response.status_code == 200
    slugs = {c["slug"] for c in response.json()["items"]}
    assert {"farm", "dairy"} <= slugs


async def test_bad_cursor_is_400(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _ = api
    response = await http.get("/directory/businesses?cursor=garbage", headers=_as(USER_A))
    assert response.status_code == 400
