"""Milk homepage blend (D23): compose covers() + milk products + geo into a
single pincode response with a 3-way scope discriminator, schema-driven
filter keys, and a price banner parsed from free-text price_display.

Milk-specific glue only — reuses covers/catalog/geo, rebuilds nothing.
The directory module must not import notify/audit/search (import-linter)."""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Protocol

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service
from modules.directory.catalog_models import Product
from modules.directory.covers import covers
from modules.directory.recommended import rank_recommended
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
    Only products in the `milk` category contribute (M1): other dairy
    categories have no milk price band and must not inflate seller_count.
    unit = the shared pack_size when uniform for that type, else None.
    seller_count = distinct businesses among the passed products.
    Products with no milk_type or no parseable ₹ number are skipped from
    bands (best-effort — price_display is free text)."""
    prices: dict[str, list[int]] = {}
    packs: dict[str, set[str]] = {}
    for p in products:
        if p.specs.get("category") not in (None, "milk"):
            continue  # ghee/paneer/... never carry a milk price band, and must
            # not inflate seller_count under a milk-only banner (M1)
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

    seller_count = len(
        {p.business_id for p in products if p.specs.get("category") in (None, "milk")}
    )
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
    product_categories: list[str]
    bands: list[PriceBand]
    seller_count: int
    vendors: list[MilkCard]
    brands: list[MilkCard]
    next_cursor: str | None
    # M3.C organic-only rail: populated exclusively by rank_recommended()
    # on the unfiltered first page; empty everywhere else.
    recommended: list[MilkCard] = dc_field(default_factory=list)


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


async def _product_category_keys(session: AsyncSession) -> list[str]:
    """Schema-driven category chips: ['all', *category options]. Same rule as
    _milk_filter_keys - the taxonomy is never hardcoded here (M1 NN#1)."""
    schema = await catalog_service.active_schema(session, "milk")
    if schema is None:
        return ["all"]
    for field in parse_fields(schema.fields):
        if field.key == "category" and field.options:
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


async def _approved_milk_products(
    session: AsyncSession, business_ids: Sequence[uuid.UUID]
) -> list[Product]:
    """The one definition of a listable milk product. Must stay in step with
    covers()' _PRODUCT_CATEGORY_PREDICATE and _COVERED_PINCODES_SQL above."""
    if not business_ids:
        return []
    return list(
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


def _group_by_business(products: Sequence[Product]) -> dict[uuid.UUID, list[Product]]:
    by_biz: dict[uuid.UUID, list[Product]] = {}
    for product in products:
        by_biz.setdefault(product.business_id, []).append(product)
    return by_biz


async def milk_home(
    session: AsyncSession,
    *,
    pincode: str,
    milk_type: str | None,
    product_category: str | None,
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
    product_categories = await _product_category_keys(session)
    # An unrecognised value is treated as absent, never a 422 (D27 precedent).
    if product_category is not None and product_category not in product_categories:
        product_category = None

    district = await district_for_pincode(session, pincode)
    if district is None:
        return MilkHomeResult(
            scope="out_of_area",
            district=None,
            state=None,
            filters=filters,
            product_categories=product_categories,
            bands=[],
            seller_count=0,
            vendors=[],
            brands=[],
            next_cursor=None,
        )
    state = await session.scalar(select(State).where(State.id == district.state_id))
    state_name = state.name if state is not None else None

    # Two covers() reads when (and only when) a product-category filter is
    # active. `scope_page` is deliberately UNFILTERED: `scope` and the price
    # banner describe coverage at this pincode, not the caller's chip, so a
    # filter that matches nothing must still yield covered + empty cards -
    # never tn_no_vendors. `page` is the filtered one and owns the cards and
    # next_cursor, so the keyset walks the FILTERED set (M1: a ghee seller
    # ranked past page 1 used to vanish behind a false empty state).
    category_filter = product_category if product_category not in (None, "all") else None
    scope_page = await covers(session, pincode=pincode, cursor=cursor, limit=limit)
    page = scope_page
    if category_filter is not None:
        page = await covers(
            session,
            pincode=pincode,
            cursor=cursor,
            limit=limit,
            product_category=category_filter,
        )

    products = await _approved_milk_products(session, [item.id for item in scope_page.items])
    # 'covered' = some business covering this pincode has a listable milk
    # product. The unfiltered window proves it; so does any row on the
    # filtered page, whose SQL predicate already demands an approved+active
    # milk product - that clause is what stops a match found deeper than the
    # unfiltered window from being discarded as tn_no_vendors.
    if not products and not (category_filter is not None and page.items):
        return MilkHomeResult(
            scope="tn_no_vendors",
            district=district.name,
            state=state_name,
            filters=filters,
            product_categories=product_categories,
            bands=[],
            seller_count=0,
            vendors=[],
            brands=[],
            next_cursor=None,
        )

    # Banner + seller_count are UNFILTERED (reflect all milk on offer here,
    # not just the chips the caller has selected).
    bands, seller_count = compute_price_banner(products)

    by_biz = _group_by_business(
        products
        if category_filter is None
        else await _approved_milk_products(session, [item.id for item in page.items])
    )

    vendors: list[MilkCard] = []
    brands: list[MilkCard] = []
    for item in page.items:
        if item.type not in _VENDOR_TYPES and item.type not in _BRAND_TYPES:
            continue  # lab (or any future non-milk-home type) - excluded entirely
        biz_products = by_biz.get(item.id)
        if not biz_products:
            continue  # covering business with no milk products -> not a card
        if product_category and product_category != "all":
            biz_products = [p for p in biz_products if p.specs.get("category") == product_category]
            if not biz_products:
                continue
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

    # M3.C: the Recommended rail rides the canonical (unfiltered, first-page)
    # view only - chip filters and cursor pages never re-rank. rank_recommended
    # is the ONLY label source; paid signals never enter it.
    recommended: list[MilkCard] = []
    unfiltered_view = (
        cursor is None
        and milk_type in (None, "all")
        and product_category in (None, "all")
        and (vendors or brands)
    )
    if unfiltered_view:
        all_cards = [*vendors, *brands]
        ranked = await rank_recommended(session, all_cards, now=datetime.now(UTC))
        by_id = {card.id: card for card in all_cards}
        recommended = [by_id[business_id] for business_id in ranked]

    return MilkHomeResult(
        scope="covered",
        district=district.name,
        state=state_name,
        filters=filters,
        product_categories=product_categories,
        bands=bands,
        seller_count=seller_count,
        vendors=vendors,
        brands=brands,
        next_cursor=page.next_cursor,
        recommended=recommended,
    )
