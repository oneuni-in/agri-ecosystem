"""Milk homepage blend (D23): compose covers() + milk products + geo into a
single pincode response with a 3-way scope discriminator, schema-driven
filter keys, and a price banner parsed from free-text price_display.

Milk-specific glue only — reuses covers/catalog/geo, rebuilds nothing.
The directory module must not import notify/audit/search (import-linter)."""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service
from modules.directory.catalog_models import Product
from modules.directory.covers import covers
from modules.directory.specs import parse_fields
from shared.geo.models import State
from shared.geo.service import district_for_pincode

_RUPEE_RE = re.compile(r"₹\s*(\d+)")
_VENDOR_TYPES = {"vendor", "farm"}
_BRAND_TYPES = {"shop"}
Scope = Literal["covered", "tn_no_vendors", "out_of_area"]


class ProductLike(Protocol):
    business_id: uuid.UUID
    specs: dict[str, object]
    price_display: str | None


@dataclass(frozen=True, slots=True)
class PriceBand:
    milk_type: str
    low: int
    high: int
    unit: str | None


def _rupees(text: str | None) -> list[int]:
    if not text:
        return []
    return [int(n) for n in _RUPEE_RE.findall(text)]


def compute_price_banner(products: Sequence[ProductLike]) -> tuple[list[PriceBand], int]:
    """Group parseable ₹ prices by milk_type → (low, high) band per type.
    unit = the shared pack_size when uniform for that type, else None.
    seller_count = distinct businesses among the passed products.
    Products with no milk_type or no parseable ₹ number are skipped from
    bands (best-effort — price_display is free text)."""
    prices: dict[str, list[int]] = {}
    packs: dict[str, set[str]] = {}
    for p in products:
        milk_type = p.specs.get("milk_type")
        nums = _rupees(p.price_display)
        if not isinstance(milk_type, str) or not milk_type or not nums:
            continue
        prices.setdefault(milk_type, []).extend(nums)
        pack = p.specs.get("pack_size")
        if isinstance(pack, str):
            packs.setdefault(milk_type, set()).add(pack)

    bands: list[PriceBand] = []
    for milk_type, nums in prices.items():
        pack_set = packs.get(milk_type, set())
        unit = next(iter(pack_set)) if len(pack_set) == 1 else None
        bands.append(PriceBand(milk_type=milk_type, low=min(nums), high=max(nums), unit=unit))

    seller_count = len({p.business_id for p in products})
    return bands, seller_count


@dataclass(frozen=True, slots=True)
class MilkCard:
    id: uuid.UUID
    name: str
    slug: str
    type: str
    verification_status: str
    subscription_tier: str
    distance_m: int
    lat: Decimal | None
    lng: Decimal | None
    products: list[Product]


@dataclass(frozen=True, slots=True)
class MilkHomeResult:
    scope: Scope
    district: str | None
    state: str | None
    filters: list[str]
    bands: list[PriceBand]
    seller_count: int
    vendors: list[MilkCard]
    brands: list[MilkCard]
    next_cursor: str | None


async def _milk_filter_keys(session: AsyncSession) -> list[str]:
    """Schema-driven chip keys: ['all', *milk_type options]. Reads the
    active D17 milk schema - never hardcoded (NON-NEGOTIABLE #2)."""
    schema = await catalog_service.active_schema(session, "milk")
    if schema is None:
        return ["all"]
    for field in parse_fields(schema.fields):
        if field.key == "milk_type" and field.options:
            return ["all", *field.options]
    return ["all"]


@dataclass(frozen=True, slots=True)
class CoveredPincode:
    pincode: str
    district: str


# Same "covered" predicate as milk_home() below (active covering business
# with >=1 approved+active milk product) - the sitemap may only advertise
# pincodes whose landing page is indexable. Raw SQL bypasses the ORM
# soft-delete filter, so deleted_at IS NULL is explicit (covers.py rule).
_COVERED_PINCODES_SQL = """
SELECT c.pincode, d.name AS district
FROM directory.business_coverage c
JOIN directory.businesses b
  ON b.id = c.business_id AND b.status = 'active' AND b.deleted_at IS NULL
JOIN geo.pincodes p ON p.pincode = c.pincode
JOIN geo.districts d ON d.id = p.district_id
WHERE EXISTS (
    SELECT 1 FROM directory.products pr
    WHERE pr.business_id = b.id AND pr.vertical_slug = 'milk'
      AND pr.moderation_status = 'approved' AND pr.status = 'active'
      AND pr.deleted_at IS NULL
)
{cursor_clause}
GROUP BY c.pincode, d.name
ORDER BY c.pincode
LIMIT :lim
"""


async def covered_pincodes(
    session: AsyncSession, *, cursor: str | None = None, limit: int = 100
) -> tuple[list[CoveredPincode], str | None]:
    """Sitemap feed (D28): keyset on pincode; the cursor IS the last pincode."""
    limit = min(max(limit, 1), 100)
    clause = "AND c.pincode > :cursor" if cursor is not None else ""
    params: dict[str, object] = {"lim": limit + 1}
    if cursor is not None:
        params["cursor"] = cursor
    rows = (
        await session.execute(text(_COVERED_PINCODES_SQL.format(cursor_clause=clause)), params)
    ).all()
    items = [
        CoveredPincode(pincode=m["pincode"], district=m["district"])
        for m in (r._mapping for r in rows[:limit])
    ]
    next_cursor = items[-1].pincode if len(rows) > limit else None
    return items, next_cursor


async def milk_home(
    session: AsyncSession,
    *,
    pincode: str,
    milk_type: str | None,
    cursor: str | None,
    limit: int,
) -> MilkHomeResult:
    """Compose covers() + milk products + geo into one pincode-scoped
    response with a 3-way scope discriminator:
      - out_of_area: district_for_pincode() found no TN district for the
        pincode (non-TN / unlisted) - NOT an error, a warm empty state.
      - tn_no_vendors: TN district resolved, but covers() has no covering
        business with an approved+active milk product.
      - covered: TN + >=1 covering business with >=1 approved+active milk
        product.
    Filter keys are always schema-driven, even in the empty-state branches,
    so the chip row never flashes/reflows once data arrives."""
    filters = await _milk_filter_keys(session)

    district = await district_for_pincode(session, pincode)
    if district is None:
        return MilkHomeResult(
            scope="out_of_area",
            district=None,
            state=None,
            filters=filters,
            bands=[],
            seller_count=0,
            vendors=[],
            brands=[],
            next_cursor=None,
        )
    state = await session.scalar(select(State).where(State.id == district.state_id))
    state_name = state.name if state is not None else None

    page = await covers(session, pincode=pincode, cursor=cursor, limit=limit)
    business_ids = [item.id for item in page.items]
    if not business_ids:
        return MilkHomeResult(
            scope="tn_no_vendors",
            district=district.name,
            state=state_name,
            filters=filters,
            bands=[],
            seller_count=0,
            vendors=[],
            brands=[],
            next_cursor=None,
        )

    products = list(
        await session.scalars(
            select(Product).where(
                Product.business_id.in_(business_ids),
                Product.vertical_slug == "milk",
                Product.moderation_status == "approved",
                Product.status == "active",
                Product.deleted_at.is_(None),
            )
        )
    )
    by_biz: dict[uuid.UUID, list[Product]] = {}
    for product in products:
        by_biz.setdefault(product.business_id, []).append(product)

    if not by_biz:
        return MilkHomeResult(
            scope="tn_no_vendors",
            district=district.name,
            state=state_name,
            filters=filters,
            bands=[],
            seller_count=0,
            vendors=[],
            brands=[],
            next_cursor=None,
        )

    # Banner + seller_count are UNFILTERED (reflect all milk on offer here,
    # not just the milk_type chip the caller has selected).
    bands, seller_count = compute_price_banner(products)

    vendors: list[MilkCard] = []
    brands: list[MilkCard] = []
    for item in page.items:
        if item.type not in _VENDOR_TYPES and item.type not in _BRAND_TYPES:
            continue  # lab (or any future non-milk-home type) - excluded entirely
        biz_products = by_biz.get(item.id)
        if not biz_products:
            continue  # covering business with no milk products -> not a card
        if milk_type and milk_type != "all":
            biz_products = [p for p in biz_products if p.specs.get("milk_type") == milk_type]
            if not biz_products:
                continue  # filtered out - scope stays 'covered', card dropped
        card = MilkCard(
            id=item.id,
            name=item.name,
            slug=item.slug,
            type=item.type,
            verification_status=item.verification_status,
            subscription_tier=item.subscription_tier,
            distance_m=item.distance_m,
            lat=item.lat,
            lng=item.lng,
            products=biz_products,
        )
        (vendors if item.type in _VENDOR_TYPES else brands).append(card)

    return MilkHomeResult(
        scope="covered",
        district=district.name,
        state=state_name,
        filters=filters,
        bands=bands,
        seller_count=seller_count,
        vendors=vendors,
        brands=brands,
        next_cursor=page.next_cursor,
    )
