"""D17 catalog router: owner-scoped product writes over HTTP (IDOR + spec
validation mapped to the right status codes) and the public SSR reads that
back Milk.in product/vertical pages. Businesses/products are seeded directly
against db_session (faster than API round-trips); routes are exercised over
HTTP through the same harness as tests/test_claims_router.py."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import catalog_service, service
from modules.directory.catalog_models import Product, Vertical
from modules.directory.models import Business
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...] = ("user",)) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str = "user") -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
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
        yield client, db_session


async def _business(
    session: AsyncSession, owner: uuid.UUID, name: str = "Coimbatore Dairy"
) -> Business:
    return await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode="641001"
    )


async def _approved_product(
    session: AsyncSession, owner: uuid.UUID, business: Business, name: str
) -> uuid.UUID:
    product = await catalog_service.create_product(
        session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name=name,
        specs={"category": "milk", "milk_type": "cow"},
    )
    await catalog_service.moderate_product(session, product_id=product.id, approve=True)
    return product.id


async def test_create_product_anon_401(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    response = await client.post(
        f"/catalog/businesses/{business.id}/products",
        json={
            "vertical_slug": "milk",
            "name": "A2 Milk",
            "specs": {"category": "milk", "milk_type": "a2"},
        },
    )
    assert response.status_code == 401


async def test_create_product_owner_pins_version(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    response = await client.post(
        f"/catalog/businesses/{business.id}/products",
        json={
            "vertical_slug": "milk",
            "name": "A2 Full Cream",
            "specs": {
                "category": "milk",
                "milk_type": "a2",
                "fat_percent": 4.5,
                "pack_size": "500ml",
            },
            "price_display": "₹80/500ml",
        },
        headers=_as(USER_A),
    )
    assert response.status_code == 201
    body = response.json()
    # M1 (0029): the active milk schema starts each test at v2 (db_session
    # rolls back per-test, so this is stable, not a race with other tests).
    assert body["schema_version"] == 2
    assert body["moderation_status"] == "pending"
    assert body["slug"] == "a2-full-cream"
    assert body["images"] == []


async def test_create_product_bad_specs_422(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    response = await client.post(
        f"/catalog/businesses/{business.id}/products",
        json={
            "vertical_slug": "milk",
            "name": "Goat Milk",
            "specs": {"category": "milk", "milk_type": "goat"},
        },
        headers=_as(USER_A),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "invalid_enum_value", "field": "milk_type"}


async def test_create_product_idor_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    response = await client.post(
        f"/catalog/businesses/{business.id}/products",
        json={
            "vertical_slug": "milk",
            "name": "Stolen",
            "specs": {"category": "milk", "milk_type": "cow"},
        },
        headers=_as(USER_B),
    )
    assert response.status_code == 404


async def test_public_product_detail_pending_then_approved(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product = await catalog_service.create_product(
        session,
        owner_user_id=USER_A,
        business_id=business.id,
        vertical_slug="milk",
        name="A2 Toned",
        specs={"category": "milk", "milk_type": "a2"},
    )
    pending = await client.get(f"/catalog/products/{product.slug}")
    assert pending.status_code == 404

    await catalog_service.moderate_product(session, product_id=product.id, approve=True)
    approved = await client.get(f"/catalog/products/{product.slug}")
    assert approved.status_code == 200
    body = approved.json()
    assert body["product"]["business_name"] == business.name
    assert body["product"]["business_slug"] == business.slug
    assert "moderation_status" not in body["product"]
    assert body["schema_fields"]
    assert isinstance(body["schema_fields"], list)


async def test_verticals_public_lists_milk(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    response = await client.get("/catalog/verticals")
    assert response.status_code == 200
    slugs = [v["slug"] for v in response.json()["items"]]
    assert "milk" in slugs


async def test_public_business_products_paginate(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    for i in range(3):
        await _approved_product(session, USER_A, business, f"Milk {i}")

    first = await client.get(f"/catalog/businesses/{business.slug}/products", params={"limit": 2})
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"] is not None

    second = await client.get(
        f"/catalog/businesses/{business.slug}/products",
        params={"limit": 2, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["next_cursor"] is None


async def test_public_vertical_products_paginate(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business = await _business(session, USER_A, "Vertical Dairy")
    for i in range(3):
        await _approved_product(session, USER_A, business, f"Vertical Milk {i}")

    first = await client.get("/catalog/verticals/milk/products", params={"limit": 2})
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"] is not None

    second = await client.get(
        "/catalog/verticals/milk/products",
        params={"limit": 2, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["next_cursor"] is None


async def test_patch_status_archived_hides_from_public_list(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business = await _business(session, USER_A, "Archive Dairy")
    product_id = await _approved_product(session, USER_A, business, "Archivable Milk")

    listed = await client.get(f"/catalog/businesses/{business.slug}/products")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    patched = await client.patch(
        f"/catalog/products/{product_id}", json={"status": "archived"}, headers=_as(USER_A)
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "archived"

    after = await client.get(f"/catalog/businesses/{business.slug}/products")
    assert after.status_code == 200
    assert after.json()["items"] == []


async def test_patch_null_name_is_400(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business = await _business(session, USER_A, "Null Name Dairy")
    product_id = await _approved_product(session, USER_A, business, "Nullable Milk")

    response = await client.patch(
        f"/catalog/products/{product_id}", json={"name": None}, headers=_as(USER_A)
    )
    assert response.status_code == 400


async def test_patch_specs_without_schema_409(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """A vertical with no published spec schema can still hold a product
    (e.g. pre-existing data from before the vertical's first schema shipped);
    a specs patch against it must map SchemaNotFoundError to 409 'no_schema',
    same as create_product does - not fall through to an unhandled 500."""
    client, session = api
    business = await _business(session, USER_A, "Seed Farm")
    # Own throwaway slug: "seeds" is a real registry row since 0037.
    session.add(Vertical(slug="seeds-nospec", name={"en": "Seeds"}, status="active"))
    await session.flush()
    product = Product(
        business_id=business.id,
        vertical_slug="seeds-nospec",
        schema_version=1,
        name="Tomato Seeds",
        slug="tomato-seeds",
        specs={},
    )
    session.add(product)
    await session.flush()
    await session.refresh(product)

    response = await client.patch(
        f"/catalog/products/{product.id}",
        json={"specs": {"variety": "hybrid"}},
        headers=_as(USER_A),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "no_schema"
