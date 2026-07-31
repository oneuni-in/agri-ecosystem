"""Wire schemas + mapper for GET /catalog/milk/home/{pincode} (D23 Task 5).

Mirrors MilkHomeResult (modules/directory/milk_home.py) field-for-field into
the public HTTP contract the web-milk frontend renders against (Task 8's
lib/milk.ts mirrors these field names). price_banner is non-null ONLY for
scope == "covered"; location is null ONLY for scope == "out_of_area"."""

import uuid
from typing import Literal

from pydantic import BaseModel

from modules.directory.milk_home import MilkCard, MilkHomeResult


class MilkProductOut(BaseModel):
    category: str | None
    milk_type: str | None
    fat_percent: float | None
    pack_size: str | None
    price_display: str | None


class MilkCardOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    type: str
    verification_status: str
    subscription_tier: str
    distance_m: int
    lat: float | None
    lng: float | None
    products: list[MilkProductOut]


class PriceBandOut(BaseModel):
    milk_type: str
    low: int
    high: int
    unit: str | None


class PriceBannerOut(BaseModel):
    lines: list[PriceBandOut]
    seller_count: int


class MilkLocationOut(BaseModel):
    pincode: str
    district: str
    state: str | None


class MilkHomeOut(BaseModel):
    scope: Literal["covered", "tn_no_vendors", "out_of_area"]
    location: MilkLocationOut | None
    filters: list[str]
    product_categories: list[str]
    price_banner: PriceBannerOut | None
    vendors: list[MilkCardOut]
    brands: list[MilkCardOut]
    next_cursor: str | None
    # M3.C: organic-only Recommended rail (rank_recommended is the sole
    # label source - paid units can never appear here).
    recommended: list[MilkCardOut] = []


class CoveredPincodeOut(BaseModel):
    pincode: str
    district: str


class CoveragePincodesOut(BaseModel):
    items: list[CoveredPincodeOut]
    next_cursor: str | None


def _card_out(card: MilkCard) -> MilkCardOut:
    return MilkCardOut(
        id=card.id,
        name=card.name,
        slug=card.slug,
        type=card.type,
        verification_status=card.verification_status,
        subscription_tier=card.subscription_tier,
        distance_m=card.distance_m,
        lat=float(card.lat) if card.lat is not None else None,
        lng=float(card.lng) if card.lng is not None else None,
        products=[
            MilkProductOut(
                category=p.specs.get("category"),
                milk_type=p.specs.get("milk_type"),
                fat_percent=p.specs.get("fat_percent"),
                pack_size=p.specs.get("pack_size"),
                price_display=p.price_display,
            )
            for p in card.products
        ],
    )


def milk_home_out(pincode: str, result: MilkHomeResult) -> MilkHomeOut:
    location = (
        MilkLocationOut(pincode=pincode, district=result.district, state=result.state)
        if result.district is not None
        else None
    )
    price_banner = (
        PriceBannerOut(
            lines=[
                PriceBandOut(milk_type=b.milk_type, low=b.low, high=b.high, unit=b.unit)
                for b in result.bands
            ],
            seller_count=result.seller_count,
        )
        if result.scope == "covered"
        else None
    )
    return MilkHomeOut(
        scope=result.scope,
        location=location,
        filters=result.filters,
        product_categories=result.product_categories,
        price_banner=price_banner,
        vendors=[_card_out(c) for c in result.vendors],
        brands=[_card_out(c) for c in result.brands],
        next_cursor=result.next_cursor,
        recommended=[_card_out(c) for c in result.recommended],
    )
