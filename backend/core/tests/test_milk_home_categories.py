"""M1 milk-home taxonomy wiring: schema-driven product_categories, the
additive ?product_category= filter (D23's ?type= is untouched), and the
price banner narrowed to category='milk' so a ghee-only seller cannot
inflate the milk seller count."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service, service
from modules.directory.milk_home import compute_price_banner, milk_home
from modules.directory.models import Business

pytestmark = pytest.mark.asyncio


@dataclass
class _P:
    business_id: uuid.UUID
    specs: dict[str, object]
    price_display: str | None


async def _vendor_with(
    session: AsyncSession, name: str, products: list[tuple[str, dict[str, object], str]]
) -> Business:
    owner = uuid.uuid4()
    business = await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode="641001"
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
    for product_name, specs, price in products:
        product = await catalog_service.create_product(
            session,
            owner_user_id=owner,
            business_id=business.id,
            vertical_slug="milk",
            name=product_name,
            specs=specs,
            price_display=price,
        )
        product.moderation_status = "approved"
    await session.flush()
    return business


async def test_product_categories_come_from_the_active_schema(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    result = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category=None,
        cursor=None,
        limit=20,
    )
    assert result.product_categories[0] == "all"
    assert "ghee" in result.product_categories
    assert "khoa" in result.product_categories


async def test_product_categories_present_in_empty_states(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """Chips must not flash/reflow when data arrives - same rule as filters."""
    out_of_area = await milk_home(
        db_session,
        pincode="110001",
        milk_type=None,
        product_category=None,
        cursor=None,
        limit=20,
    )
    assert out_of_area.scope == "out_of_area"
    assert "ghee" in out_of_area.product_categories
    no_vendors = await milk_home(
        db_session,
        pincode="600001",
        milk_type=None,
        product_category=None,
        cursor=None,
        limit=20,
    )
    assert no_vendors.scope == "tn_no_vendors"
    assert "ghee" in no_vendors.product_categories


async def test_product_category_narrows_cards(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _vendor_with(
        db_session, "MilkOnly", [("Cow Milk", {"category": "milk", "milk_type": "cow"}, "₹50/L")]
    )
    await _vendor_with(db_session, "GheeOnly", [("Pure Ghee", {"category": "ghee"}, "₹600/500ml")])
    ghee = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category="ghee",
        cursor=None,
        limit=20,
    )
    assert [v.name for v in ghee.vendors] == ["GheeOnly"]
    assert ghee.scope == "covered"


async def test_unknown_product_category_is_treated_as_absent(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """D27 precedent: an unrecognised value is not a 422."""
    await _vendor_with(
        db_session, "MilkOnly", [("Cow Milk", {"category": "milk", "milk_type": "cow"}, "₹50/L")]
    )
    result = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category="not-a-category",
        cursor=None,
        limit=20,
    )
    assert [v.name for v in result.vendors] == ["MilkOnly"]


async def test_type_and_product_category_compose(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _vendor_with(
        db_session,
        "Both",
        [
            ("Cow Milk", {"category": "milk", "milk_type": "cow"}, "₹50/L"),
            ("Pure Ghee", {"category": "ghee"}, "₹600/500ml"),
        ],
    )
    result = await milk_home(
        db_session,
        pincode="641001",
        milk_type="cow",
        product_category="milk",
        cursor=None,
        limit=20,
    )
    assert [p.name for p in result.vendors[0].products] == ["Cow Milk"]


def test_price_banner_ignores_non_milk_products() -> None:
    """seller_count must reflect milk sellers, not every dairy seller."""
    milk_seller, ghee_seller = uuid.uuid4(), uuid.uuid4()
    bands, sellers = compute_price_banner(
        [
            _P(milk_seller, {"category": "milk", "milk_type": "cow", "pack_size": "1l"}, "₹50/L"),
            _P(ghee_seller, {"category": "ghee"}, "₹600/500ml"),
        ]
    )
    assert [b.milk_type for b in bands] == ["cow"]
    assert sellers == 1
