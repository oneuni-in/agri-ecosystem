"""Directory API: auth gate, IDOR via the API (non-negotiable #2), rename ->
301 wiring, public detail + covers routes, public-route registry entries.

Principal injection mirrors test_coins_router.py; the x-test-user header picks
the acting user so one client can exercise the IDOR matrix."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import service
from shared.db import get_session
from shared.middleware import SlugRedirectMiddleware
from shared.security import register_principal_resolver
from shared.slugs import find_redirect

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


async def test_public_detail_by_slug(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _ = api
    created = await http.post("/directory/businesses", json=CREATE_BODY, headers=_as(USER_A))
    slug = created.json()["slug"]
    detail = await http.get(f"/directory/businesses/{slug}")  # public: NO auth header
    assert detail.status_code == 200
    body = detail.json()
    assert body["business"]["name"] == "Anbu Milk Farm"
    assert body["branches"] == []
    assert body["categories"] == []
    assert (await http.get("/directory/businesses/no-such-slug")).status_code == 404


async def test_covers_endpoint_public(
    api: tuple[httpx.AsyncClient, AsyncSession], tn_geo_sample: None
) -> None:
    http, session = api
    owner = uuid.uuid4()
    business = await service.create_business(
        session, owner_user_id=owner, name="Near Farm", type_="vendor", primary_pincode="641001"
    )
    await service.set_coverage(
        session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    response = await http.get("/directory/covers/641001")  # public: NO auth header
    assert response.status_code == 200
    body = response.json()
    assert [item["slug"] for item in body["items"]] == ["near-farm"]
    assert body["items"][0]["distance_m"] >= 0
    assert body["next_cursor"] is None
    assert (await http.get("/directory/covers/641001?cursor=garbage")).status_code == 400
    assert (await http.get("/directory/covers/notapin")).status_code == 422


async def test_rename_serves_301_from_old_path(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    created = await http.post("/directory/businesses", json=CREATE_BODY, headers=_as(USER_A))
    business_id = created.json()["id"]
    renamed = await http.post(
        f"/directory/businesses/{business_id}/rename",
        json={"new_slug": "anbu-dairy"},
        headers=_as(USER_A),
    )
    assert renamed.status_code == 200
    assert renamed.json()["slug"] == "anbu-dairy"
    # 1. the redirect row is recorded with the canonical public paths
    assert (
        await find_redirect(session, "/directory/businesses/anbu-milk-farm")
        == "/directory/businesses/anbu-dairy"
    )
    # 2. the middleware serves that mapping as a 301. Lookup is injected here
    #    because the app-level middleware opens its own DB session, which
    #    cannot see this test's rolled-back transaction (same split as
    #    test_slugs.py).
    redirects = {"/directory/businesses/anbu-milk-farm": "/directory/businesses/anbu-dairy"}

    async def lookup(path: str) -> str | None:
        return redirects.get(path)

    plain = FastAPI()
    plain.add_middleware(SlugRedirectMiddleware, lookup=lookup)
    client = TestClient(plain, follow_redirects=False)
    response = client.get("/directory/businesses/anbu-milk-farm")
    assert response.status_code == 301
    assert response.headers["location"] == "/directory/businesses/anbu-dairy"
    # 3. old slug 404s at the API (which is what arms the middleware); new slug 200s
    assert (await http.get("/directory/businesses/anbu-milk-farm")).status_code == 404
    assert (await http.get("/directory/businesses/anbu-dairy")).status_code == 200


def test_directory_public_routes_are_registered() -> None:
    app = create_app()
    assert "/directory/businesses/{slug}" in app.state.public_routes
    assert "/directory/covers/{pincode}" in app.state.public_routes
