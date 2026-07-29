import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import catalog_service, service
from modules.directory import milk_home as milk_home_mod
from modules.directory.milk_home import PriceBand, ProductLike, compute_price_banner
from modules.directory.models import Business
from shared.db import get_session
from shared.security import register_principal_resolver


class _Principal:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.roles = ("user",)


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        return _Principal(uuid.UUID(header)) if header else None

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as http:
        yield http


@dataclass
class _P:
    business_id: uuid.UUID
    specs: dict[str, object]
    price_display: str | None


def _biz() -> uuid.UUID:
    return uuid.uuid4()


def test_price_banner_groups_by_type_and_ranges() -> None:
    b1, b2 = _biz(), _biz()
    products: list[ProductLike] = [
        _P(b1, {"milk_type": "cow", "pack_size": "1l"}, "₹52/L"),
        _P(b2, {"milk_type": "cow", "pack_size": "1l"}, "₹60/L"),
        _P(b1, {"milk_type": "buffalo", "pack_size": "1l"}, "₹68/L"),
    ]
    bands, seller_count = compute_price_banner(products)
    by_type = {b.milk_type: b for b in bands}
    assert by_type["cow"] == PriceBand(milk_type="cow", low=52, high=60, unit="1l")
    assert by_type["buffalo"] == PriceBand(milk_type="buffalo", low=68, high=68, unit="1l")
    assert seller_count == 2  # two distinct businesses


def test_price_banner_skips_unparseable_and_typeless() -> None:
    b = _biz()
    products: list[ProductLike] = [
        _P(b, {"milk_type": "cow", "pack_size": "1l"}, "call for price"),  # no ₹number
        _P(b, {"pack_size": "1l"}, "₹40/L"),  # no milk_type
        _P(b, {"milk_type": "a2", "pack_size": "500ml"}, "₹95/500ml"),
    ]
    bands, seller_count = compute_price_banner(products)
    assert [b.milk_type for b in bands] == ["a2"]
    assert bands[0] == PriceBand(milk_type="a2", low=95, high=95, unit="500ml")
    assert seller_count == 1


def test_price_banner_unit_none_when_pack_sizes_differ() -> None:
    b = _biz()
    products: list[ProductLike] = [
        _P(b, {"milk_type": "cow", "pack_size": "1l"}, "₹52/L"),
        _P(b, {"milk_type": "cow", "pack_size": "500ml"}, "₹28/500ml"),
    ]
    bands, _ = compute_price_banner(products)
    assert bands[0].unit is None  # mixed pack sizes → no single unit


@pytest.mark.asyncio
async def test_milk_home_out_of_area_non_tn(db_session: AsyncSession) -> None:
    # 110001 (Delhi) is not present in the geo fixture at all -> non-TN.
    result = await milk_home_mod.milk_home(
        db_session, pincode="110001", milk_type=None, product_category=None, cursor=None, limit=20
    )
    assert result.scope == "out_of_area"
    assert result.district is None
    assert result.vendors == [] and result.brands == []
    # filters are still schema-driven even when out of area
    assert result.filters[0] == "all"
    assert "cow" in result.filters


@pytest.mark.asyncio
async def test_milk_home_tn_no_vendors(db_session: AsyncSession, tn_geo_sample: None) -> None:
    # 600001 (Chennai) is a TN pincode present in the geo fixture with NO
    # business_coverage row - proven by test_directory_covers.py, where every
    # covered business in the fixture covers 641001, never 600001.
    result = await milk_home_mod.milk_home(
        db_session, pincode="600001", milk_type=None, product_category=None, cursor=None, limit=20
    )
    assert result.scope == "tn_no_vendors"
    assert result.district is not None  # geo resolved a TN district
    assert result.vendors == [] and result.brands == []


@pytest.mark.asyncio
async def test_milk_home_covered(db_session: AsyncSession, seed_milk_vendor: object) -> None:
    # seed_milk_vendor fixture: a `vendor` covering 641001 with ≥1 approved milk product
    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, product_category=None, cursor=None, limit=20
    )
    assert result.scope == "covered"
    assert result.seller_count >= 1
    assert len(result.vendors) >= 1
    assert result.bands, "price banner computed from real listings"


@pytest.mark.asyncio
async def test_milk_home_tn_no_vendors_when_no_qualifying_product(
    db_session: AsyncSession, seed_milk_vendor_unapproved: Business
) -> None:
    # seed_milk_vendor_unapproved: covers() returns the business (business_ids
    # non-empty), but its only product is left `pending` (never moderated) -
    # by_biz ends up empty. This is the SECOND tn_no_vendors branch, distinct
    # from the covers()-empty case in test_milk_home_tn_no_vendors above.
    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, product_category=None, cursor=None, limit=20
    )
    assert result.scope == "tn_no_vendors"
    assert result.district is not None
    assert result.vendors == [] and result.brands == []


@pytest.mark.asyncio
async def test_milk_home_filter_zero_matches_keeps_covered_scope(
    db_session: AsyncSession, seed_milk_vendor: object
) -> None:
    # seed_milk_vendor only stocks "cow" and "buffalo" milk_type products.
    # "a2" is a valid schema option the vendor does NOT stock: filtering must
    # drop the card, never flip the scope away from 'covered'.
    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type="a2", product_category=None, cursor=None, limit=20
    )
    assert result.scope == "covered"
    assert result.vendors == [] and result.brands == []


@pytest.mark.asyncio
async def test_milk_home_covered_excludes_unapproved_product(
    db_session: AsyncSession, seed_milk_vendor: Business
) -> None:
    # Add a second, UNAPPROVED (pending) product to the same seeded business.
    # This proves only the `moderation_status == "approved"` predicate is
    # load-bearing here - it says nothing about the `status == "active"` or
    # `deleted_at IS NULL` predicates, which are covered separately by
    # test_milk_home_excludes_archived_product and
    # test_milk_home_excludes_soft_deleted_product below.
    assert seed_milk_vendor.owner_user_id is not None
    await catalog_service.create_product(
        db_session,
        owner_user_id=seed_milk_vendor.owner_user_id,
        business_id=seed_milk_vendor.id,
        vertical_slug="milk",
        name="Unapproved A2 Milk",
        specs={"category": "milk", "milk_type": "a2", "fat_percent": 4.5, "pack_size": "1l"},
        price_display="₹999/1l",
    )
    # deliberately not moderated - stays `pending`

    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, product_category=None, cursor=None, limit=20
    )
    assert result.scope == "covered"
    names = {p.name for card in result.vendors for p in card.products}
    assert "Unapproved A2 Milk" not in names
    assert all(b.milk_type != "a2" for b in result.bands)


@pytest.mark.asyncio
async def test_milk_home_excludes_archived_product(
    db_session: AsyncSession, seed_milk_vendor: Business
) -> None:
    # Add a third product, approved but with status="archived" (a real value
    # of the product_status enum - see catalog_models.py). This is the only
    # predicate in milk_home()'s product query that guards against archived
    # listings, so this proves `Product.status == "active"` is load-bearing:
    # dropping it from the query would leak this product into the card.
    assert seed_milk_vendor.owner_user_id is not None
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=seed_milk_vendor.owner_user_id,
        business_id=seed_milk_vendor.id,
        vertical_slug="milk",
        name="Archived A2 Milk",
        specs={"category": "milk", "milk_type": "a2", "fat_percent": 4.5, "pack_size": "1l"},
        price_display="₹999/1l",
    )
    await catalog_service.moderate_product(db_session, product_id=product.id, approve=True)
    product.status = "archived"
    await db_session.flush()

    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, product_category=None, cursor=None, limit=20
    )
    assert result.scope == "covered"
    names = {p.name for card in result.vendors for p in card.products}
    assert "Archived A2 Milk" not in names
    assert all(b.milk_type != "a2" for b in result.bands)


@pytest.mark.asyncio
async def test_milk_home_excludes_soft_deleted_product(
    db_session: AsyncSession, seed_milk_vendor: Business
) -> None:
    # Add a fourth product, approved and active, but with deleted_at set to a
    # real (non-null) timestamp. Note: shared/db.py's global do_orm_execute
    # listener already injects a `deleted_at IS NULL` loader criteria for
    # every SoftDeleteMixin select, so this exclusion is enforced twice over -
    # this test proves the *behavior*, not that milk_home()'s local
    # `Product.deleted_at.is_(None)` predicate specifically is load-bearing
    # (removing just that local predicate would not change this outcome).
    assert seed_milk_vendor.owner_user_id is not None
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=seed_milk_vendor.owner_user_id,
        business_id=seed_milk_vendor.id,
        vertical_slug="milk",
        name="Deleted A2 Milk",
        specs={"category": "milk", "milk_type": "a2", "fat_percent": 4.5, "pack_size": "1l"},
        price_display="₹999/1l",
    )
    await catalog_service.moderate_product(db_session, product_id=product.id, approve=True)
    product.deleted_at = datetime.now(UTC)
    await db_session.flush()

    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, product_category=None, cursor=None, limit=20
    )
    assert result.scope == "covered"
    names = {p.name for card in result.vendors for p in card.products}
    assert "Deleted A2 Milk" not in names
    assert all(b.milk_type != "a2" for b in result.bands)


@pytest.mark.asyncio
async def test_milk_home_excludes_lab_businesses(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    # A `lab` business with an approved milk product must not appear in
    # either vendors or brands - it is excluded from the milk home entirely.
    owner = uuid.uuid4()
    business = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Coimbatore Dairy Test Lab",
        type_="lab",
        primary_pincode="641001",
    )
    await service.add_branch(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        address="9 Race Course Road, Coimbatore",
        state="Tamil Nadu",
        district="Coimbatore",
        pincode="641001",
        lat=Decimal("10.923220"),
        lng=Decimal("76.968600"),
    )
    await service.set_coverage(
        db_session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="Lab Test Milk Sample",
        specs={"category": "milk", "milk_type": "cow", "fat_percent": 4.0, "pack_size": "500ml"},
        price_display="₹35/500ml",
    )
    await catalog_service.moderate_product(db_session, product_id=product.id, approve=True)

    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, product_category=None, cursor=None, limit=20
    )
    assert result.scope == "covered"
    ids = {c.id for c in (*result.vendors, *result.brands)}
    assert business.id not in ids


@pytest.mark.asyncio
async def test_milk_home_filters_match_schema(db_session: AsyncSession) -> None:
    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, product_category=None, cursor=None, limit=20
    )
    from modules.directory.specs import parse_fields

    schema = await catalog_service.active_schema(db_session, "milk")
    assert schema is not None
    options = next(f.options for f in parse_fields(schema.fields) if f.key == "milk_type")
    assert options is not None
    assert result.filters == ["all", *options]


@pytest.mark.asyncio
async def test_http_milk_home_out_of_area(client: httpx.AsyncClient) -> None:
    resp = await client.get("/catalog/milk/home/110001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "out_of_area"
    assert body["location"] is None
    assert body["filters"][0] == "all"


@pytest.mark.asyncio
async def test_http_milk_home_tn_no_vendors(client: httpx.AsyncClient, tn_geo_sample: None) -> None:
    resp = await client.get("/catalog/milk/home/600001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "tn_no_vendors"
    assert body["location"]["district"] is not None
    assert body["vendors"] == [] and body["brands"] == []


@pytest.mark.asyncio
async def test_http_milk_home_covered(client: httpx.AsyncClient, seed_milk_vendor: object) -> None:
    resp = await client.get("/catalog/milk/home/641001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "covered"
    assert len(body["vendors"]) >= 1
    assert body["price_banner"]["seller_count"] >= 1
    assert body["price_banner"]["lines"], "banner computed from listings"


@pytest.mark.asyncio
async def test_http_milk_home_bad_pincode_422(client: httpx.AsyncClient) -> None:
    resp = await client.get("/catalog/milk/home/64100")
    assert resp.status_code == 422  # Path pattern ^\d{6}$


@pytest.mark.asyncio
async def test_milk_home_cards_carry_branch_coords(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    owner = uuid.uuid4()
    business = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Geo Dairy",
        type_="vendor",
        primary_pincode="641001",
    )
    await service.set_coverage(
        db_session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    await service.add_branch(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        address="1 Main Rd",
        state="Tamil Nadu",
        district="Coimbatore",
        pincode="641001",
        lat=Decimal("10.923220"),
        lng=Decimal("76.968600"),
    )
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="Cow Milk",
        specs={"category": "milk", "milk_type": "cow", "fat_percent": 4.0, "pack_size": "1l"},
        price_display="₹55/L",
    )
    await catalog_service.moderate_product(db_session, product_id=product.id, approve=True)

    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, product_category=None, cursor=None, limit=20
    )
    assert result.scope == "covered"
    card = result.vendors[0]
    assert card.lat is not None and float(card.lat) == pytest.approx(10.92322, abs=1e-4)
    assert card.lng is not None and float(card.lng) == pytest.approx(76.9686, abs=1e-4)
