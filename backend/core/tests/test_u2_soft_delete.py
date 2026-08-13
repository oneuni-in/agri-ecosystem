"""U2 Group B — owner soft-delete for businesses (listings) and products.

The binding mutation check: a soft-deleted listing vanishes from every
public read immediately, remains recoverable under `include_deleted=True`,
and the DELETE verbs never hard-delete anything (Constitution soft-delete).
"""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import catalog_service
from modules.directory import service as directory_service
from modules.directory.catalog_models import Product
from modules.directory.models import Business
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

OWNER = uuid.uuid4()


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


async def _seed(session: AsyncSession) -> tuple[Business, Product]:
    business = await directory_service.create_business(
        session,
        owner_user_id=OWNER,
        name="Erode Soft Delete Dairy",
        type_="vendor",
        primary_pincode="638001",
    )
    product = await catalog_service.create_product(
        session,
        owner_user_id=OWNER,
        business_id=business.id,
        vertical_slug="milk",
        name="Erode Cow Milk",
        specs={"category": "milk", "milk_type": "cow"},
    )
    await session.flush()
    return business, product


async def test_business_soft_delete_roundtrip(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    business, _ = await _seed(session)
    slug = business.slug

    # public + owner reads see it before the delete
    assert (await http.get(f"/directory/businesses/{slug}")).status_code == 200
    listed = await http.get("/directory/businesses", headers=_as(OWNER))
    assert any(row["slug"] == slug for row in listed.json()["items"])

    deleted = await http.delete(f"/directory/businesses/{business.id}", headers=_as(OWNER))
    assert deleted.status_code == 204

    # gone from the public page, the owner list, and every write path…
    assert (await http.get(f"/directory/businesses/{slug}")).status_code == 404
    relisted = await http.get("/directory/businesses", headers=_as(OWNER))
    assert not any(row["slug"] == slug for row in relisted.json()["items"])
    again = await http.delete(f"/directory/businesses/{business.id}", headers=_as(OWNER))
    assert again.status_code == 404  # a deleted row reads as absent, even to its owner

    # …but the ROW still exists: soft delete, restorable by support.
    # include_deleted justification: this test IS the recoverability proof —
    # it asserts the DELETE verb never hard-deletes (admin/moderation escape
    # hatch, backend-conventions.md).
    row = await session.scalar(
        select(Business).where(Business.id == business.id).execution_options(include_deleted=True)
    )
    assert row is not None
    assert row.deleted_at is not None


async def test_product_soft_delete_roundtrip(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    business, product = await _seed(session)

    deleted = await http.delete(f"/catalog/products/{product.id}", headers=_as(OWNER))
    assert deleted.status_code == 204

    # gone from the owner list and from the owner's write paths
    mine = await http.get(f"/catalog/my/products?business_id={business.id}", headers=_as(OWNER))
    assert not any(row["id"] == str(product.id) for row in mine.json()["items"])
    assert (
        await http.patch(
            f"/catalog/products/{product.id}",
            json={"price_display": "₹9/L"},
            headers=_as(OWNER),
        )
    ).status_code == 404

    # gone from the public product page
    assert (await http.get(f"/catalog/products/{product.slug}")).status_code == 404

    # include_deleted justification: recoverability proof — the row survives
    # the DELETE verb (soft delete, support can restore).
    row = await session.scalar(
        select(Product).where(Product.id == product.id).execution_options(include_deleted=True)
    )
    assert row is not None
    assert row.deleted_at is not None
