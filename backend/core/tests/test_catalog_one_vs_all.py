"""M1 NON-NEGOTIABLE 3 (spec item 4): a brand selling ONE product and a brand
selling ALL of them both render correctly. Built on real seed-shaped data,
not synthetic scaffolding."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service, service
from modules.directory.milk_home import milk_home
from modules.directory.specs import parse_fields

pytestmark = pytest.mark.asyncio


async def _all_categories(session: AsyncSession) -> list[str]:
    schema = await catalog_service.active_schema(session, "milk")
    assert schema is not None
    field = next(f for f in parse_fields(schema.fields) if f.key == "category")
    assert field.options is not None
    return list(field.options)


async def _brand(session: AsyncSession, name: str, categories: list[str]) -> tuple[uuid.UUID, str]:
    owner = uuid.uuid4()
    business = await service.create_business(
        session, owner_user_id=owner, name=name, type_="shop", primary_pincode="641001"
    )
    await service.set_coverage(
        session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    await service.add_branch(
        session,
        owner_user_id=owner,
        business_id=business.id,
        address="1 Main Rd",
        state="Tamil Nadu",
        district="Coimbatore",
        pincode="641001",
        lat=Decimal("10.9232"),
        lng=Decimal("76.9686"),
    )
    for category in categories:
        specs: dict[str, object] = {"category": category}
        if category == "milk":
            specs["milk_type"] = "cow"
        product = await catalog_service.create_product(
            session,
            owner_user_id=owner,
            business_id=business.id,
            vertical_slug="milk",
            name=f"{name} {category}",
            specs=specs,
            price_display="₹100",
        )
        product.moderation_status = "approved"
    await session.flush()
    return business.id, business.slug


async def test_one_product_brand_renders(db_session: AsyncSession, tn_geo_sample: None) -> None:
    _, slug = await _brand(db_session, "Kovai Ghee House", ["ghee"])
    page = await catalog_service.list_business_products(db_session, slug)
    assert len(page.items) == 1
    assert page.items[0].specs["category"] == "ghee"


async def test_all_products_brand_renders(db_session: AsyncSession, tn_geo_sample: None) -> None:
    categories = await _all_categories(db_session)
    _, slug = await _brand(db_session, "Coimbatore Dairy Mart", categories)
    page = await catalog_service.list_business_products(db_session, slug, limit=100)
    assert {p.specs["category"] for p in page.items} == set(categories)


async def test_both_brands_appear_on_their_category_pages(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    categories = await _all_categories(db_session)
    await _brand(db_session, "Kovai Ghee House", ["ghee"])
    await _brand(db_session, "Coimbatore Dairy Mart", categories)
    ghee = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category="ghee",
        cursor=None,
        limit=50,
    )
    assert {b.name for b in ghee.brands} == {"Kovai Ghee House", "Coimbatore Dairy Mart"}
    khoa = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category="khoa",
        cursor=None,
        limit=50,
    )
    assert {b.name for b in khoa.brands} == {"Coimbatore Dairy Mart"}


async def test_one_product_brand_is_absent_from_other_categories(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _brand(db_session, "Kovai Ghee House", ["ghee"])
    paneer = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category="paneer",
        cursor=None,
        limit=50,
    )
    assert paneer.brands == []
