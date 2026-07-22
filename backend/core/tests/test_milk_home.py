import uuid
from dataclasses import dataclass

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
