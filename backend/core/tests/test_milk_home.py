import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import milk_home as milk_home_mod
from modules.directory.milk_home import PriceBand, ProductLike, compute_price_banner


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
        db_session, pincode="110001", milk_type=None, cursor=None, limit=20
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
        db_session, pincode="600001", milk_type=None, cursor=None, limit=20
    )
    assert result.scope == "tn_no_vendors"
    assert result.district is not None  # geo resolved a TN district
    assert result.vendors == [] and result.brands == []


@pytest.mark.asyncio
async def test_milk_home_covered(db_session: AsyncSession, seed_milk_vendor: object) -> None:
    # seed_milk_vendor fixture: a `vendor` covering 641001 with ≥1 approved milk product
    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, cursor=None, limit=20
    )
    assert result.scope == "covered"
    assert result.seller_count >= 1
    assert len(result.vendors) >= 1
    assert result.bands, "price banner computed from real listings"


@pytest.mark.asyncio
async def test_milk_home_filters_match_schema(db_session: AsyncSession) -> None:
    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, cursor=None, limit=20
    )
    from modules.directory import catalog_service
    from modules.directory.specs import parse_fields

    schema = await catalog_service.active_schema(db_session, "milk")
    assert schema is not None
    options = next(f.options for f in parse_fields(schema.fields) if f.key == "milk_type")
    assert options is not None
    assert result.filters == ["all", *options]
