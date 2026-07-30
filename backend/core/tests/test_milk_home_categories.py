"""M1 milk-home taxonomy wiring: schema-driven product_categories, the
additive ?product_category= filter (D23's ?type= is untouched), and the
price banner narrowed to category='milk' so a ghee-only seller cannot
inflate the milk seller count."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service, service
from modules.directory.covers import covers
from modules.directory.milk_home import compute_price_banner, milk_home
from modules.directory.models import Business, Category

pytestmark = pytest.mark.asyncio


@dataclass
class _P:
    business_id: uuid.UUID
    specs: dict[str, object]
    price_display: str | None


async def _vendor_with(
    session: AsyncSession,
    name: str,
    products: list[tuple[str, dict[str, object], str]],
    *,
    lat: str = "10.9232",
    lng: str = "76.9686",
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
        lat=Decimal(lat),
        lng=Decimal(lng),
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


_MILK: tuple[str, dict[str, object], str] = (
    "Cow Milk",
    {"category": "milk", "milk_type": "cow"},
    "₹50/L",
)
_GHEE: tuple[str, dict[str, object], str] = ("Pure Ghee", {"category": "ghee"}, "₹600/500ml")


async def test_product_category_filter_reaches_sellers_beyond_the_first_page(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """The M1 defect: the filter used to be applied in Python to the already
    truncated covers() page, so a ghee seller that ranks past page 1 by
    distance produced a FALSE empty state at a covered pincode. The filter
    must be pushed into the covers() SQL so pagination walks the FILTERED set.
    Three milk-only vendors sit on the 641001 centroid; the only ghee seller
    is ~65 km away, i.e. 4th by distance and outside a limit=2 page 1."""
    for i in range(3):
        await _vendor_with(db_session, f"Near Milk {i}", [_MILK])
    await _vendor_with(db_session, "Far Ghee House", [_GHEE], lat="11.5000", lng="77.5000")

    unfiltered = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category=None,
        cursor=None,
        limit=2,
    )
    # Precondition: the ghee seller genuinely does not rank on page 1.
    assert "Far Ghee House" not in [v.name for v in unfiltered.vendors]
    assert unfiltered.next_cursor is not None

    ghee = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category="ghee",
        cursor=None,
        limit=2,
    )
    assert ghee.scope == "covered"
    assert [v.name for v in ghee.vendors] == ["Far Ghee House"]
    assert ghee.next_cursor is None  # the filtered set is exhausted in one page


async def test_filtered_match_survives_a_product_less_unfiltered_window(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """Same defect one page deeper: the unfiltered window that decides `scope`
    can be full of covering businesses with no listable milk at all. A row on
    the filtered page is itself proof of coverage (covers()' product predicate
    demands approved+active milk), so it must not be thrown away as
    tn_no_vendors."""
    await _vendor_with(db_session, "Empty Shopfront", [])  # covers 641001, sells nothing
    await _vendor_with(db_session, "Far Ghee House", [_GHEE], lat="11.5000", lng="77.5000")

    unfiltered = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category=None,
        cursor=None,
        limit=1,
    )
    # Pre-existing, unchanged: the discriminator is scoped to the page.
    assert unfiltered.scope == "tn_no_vendors"

    ghee = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category="ghee",
        cursor=None,
        limit=1,
    )
    assert ghee.scope == "covered"
    assert [v.name for v in ghee.vendors] == ["Far Ghee House"]


async def test_product_category_filter_composes_with_business_category(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """covers()' D27 `category` (business category) and M1's `product_category`
    must AND together - neither may overwrite the other."""
    farm = await _vendor_with(db_session, "Ghee Farm", [_GHEE])
    other = await _vendor_with(db_session, "Ghee Shop", [_GHEE])
    milk_farm = await _vendor_with(db_session, "Milk Farm", [_MILK])
    dairy_farm_id = await db_session.scalar(
        select(Category.id).where(Category.slug == "dairy-farm")
    )
    assert dairy_farm_id is not None
    for business in (farm, milk_farm):
        assert business.owner_user_id is not None
        await service.assign_categories(
            db_session,
            owner_user_id=business.owner_user_id,
            business_id=business.id,
            category_ids=[dairy_farm_id],
        )

    both = await covers(
        db_session, pincode="641001", category="dairy-farm", product_category="ghee"
    )
    assert {i.name for i in both.items} == {"Ghee Farm"}
    # each predicate on its own still selects a strictly wider set
    by_business = await covers(db_session, pincode="641001", category="dairy-farm")
    assert {i.name for i in by_business.items} == {"Ghee Farm", "Milk Farm"}
    by_product = await covers(db_session, pincode="641001", product_category="ghee")
    assert {i.name for i in by_product.items} == {"Ghee Farm", "Ghee Shop"}
    assert other.id in {i.id for i in by_product.items}


async def test_product_category_zero_matches_keeps_covered_scope(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """Scope describes coverage at the pincode, not the caller's filter (the
    same contract test_milk_home_filter_zero_matches_keeps_covered_scope
    asserts for ?type=). price_banner/seller_count stay UNFILTERED too."""
    await _vendor_with(db_session, "MilkOnly", [_MILK])
    result = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category="paneer",
        cursor=None,
        limit=20,
    )
    assert result.scope == "covered"
    assert result.vendors == [] and result.brands == []
    assert [b.milk_type for b in result.bands] == ["cow"]  # banner ignores the filter
    assert result.seller_count == 1


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
