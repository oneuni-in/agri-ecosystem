"""Search snapshots: the ONLY builder of index-worthy event payloads (ADR-0007).

Directory owns what is publicly indexable; modules/search (D19, a later task)
owns the index and consumes the "directory" event stream - it must NEVER read
directory tables directly. Every business.*/product.* event this module's
routers publish therefore carries a complete, self-contained "snapshot": null
when the row is not publicly visible, otherwise a PII-free dict the search
indexer can write verbatim (plus its own allowlist).

Visibility: a business is visible iff status == 'active' and not soft-deleted;
a product is visible iff moderation_status == 'approved', status == 'active',
not soft-deleted, AND its parent business is visible.

Forbidden anywhere in a snapshot (recursive): phone, whatsapp, email,
owner_user_id, phone_last4 - never add a field without checking this list.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.geo.models import District, Pincode, State

from .catalog_models import Product
from .models import Branch, Business, BusinessCategory, BusinessCoverage, Category

SITES = ("agri", "milk")
# Category slugs that pull a business into a vertical site even before it has
# any approved product in that vertical (e.g. a seeded dairy business should
# show up on Milk.in as soon as it's categorized, not only after its first
# product clears moderation).
CATEGORY_SITES: dict[str, str] = {"dairy": "milk"}


async def _geo_context(
    session: AsyncSession, pincode: str
) -> tuple[str | None, str | None, dict[str, float] | None]:
    row = (
        await session.execute(
            select(District.name, State.name, Pincode.centroid_lat, Pincode.centroid_lon)
            .join(District, Pincode.district_id == District.id)
            .join(State, District.state_id == State.id)
            .where(Pincode.pincode == pincode)
        )
    ).first()
    if row is None:
        return None, None, None
    district, state, lat, lon = row
    return district, state, {"lat": float(lat), "lng": float(lon)}


async def business_snapshot(session: AsyncSession, business_id: uuid.UUID) -> dict[str, Any] | None:
    """None when the business isn't publicly visible; otherwise a PII-free dict."""
    biz = await session.get(Business, business_id)
    if biz is None or biz.deleted_at is not None or biz.status != "active":
        return None
    district, state, centroid = await _geo_context(session, biz.primary_pincode)
    branch_geo = (
        await session.execute(
            select(Branch.lat, Branch.lng)
            .where(
                Branch.business_id == business_id,
                Branch.deleted_at.is_(None),
                Branch.lat.is_not(None),
                Branch.lng.is_not(None),
            )
            .order_by(Branch.id)
            .limit(1)
        )
    ).first()
    geo = {"lat": float(branch_geo[0]), "lng": float(branch_geo[1])} if branch_geo else centroid
    categories = list(
        (
            await session.execute(
                select(Category.slug)
                .join(BusinessCategory, BusinessCategory.category_id == Category.id)
                .where(BusinessCategory.business_id == business_id)
            )
        ).scalars()
    )
    covered = list(
        (
            await session.execute(
                select(BusinessCoverage.pincode).where(BusinessCoverage.business_id == business_id)
            )
        ).scalars()
    )
    sites = ["agri"]
    for slug in categories:
        site = CATEGORY_SITES.get(slug)
        if site and site not in sites:
            sites.append(site)
    product_verticals = (
        await session.execute(
            select(Product.vertical_slug)
            .where(
                Product.business_id == business_id,
                Product.deleted_at.is_(None),
                Product.status == "active",
                Product.moderation_status == "approved",
            )
            .distinct()
        )
    ).scalars()
    for vertical in product_verticals:
        if vertical in SITES and vertical not in sites:
            sites.append(vertical)
    return {
        "id": f"business_{biz.id.hex}",
        "kind": "business",
        "sites": sites,
        "name": biz.name,
        "slug": biz.slug,
        "description": biz.description.to_dict() if biz.description else None,
        "categories": categories,
        "district": district,
        "state": state,
        "covered_pincodes": covered,
        "verified": biz.verification_status == "verified",
        "_geo": geo,
    }


async def product_snapshot(session: AsyncSession, product_id: uuid.UUID) -> dict[str, Any] | None:
    """None when the product isn't publicly visible (own state OR its business's)."""
    prod = await session.get(Product, product_id)
    if (
        prod is None
        or prod.deleted_at is not None
        or prod.status != "active"
        or prod.moderation_status != "approved"
    ):
        return None
    parent = await business_snapshot(session, prod.business_id)
    if parent is None:
        return None
    sites = ["agri"]
    if prod.vertical_slug in SITES:
        sites.append(prod.vertical_slug)
    return {
        "id": f"product_{prod.id.hex}",
        "kind": "product",
        "sites": sites,
        "name": prod.name,
        "slug": prod.slug,
        "business_name": parent["name"],
        "business_slug": parent["slug"],
        "vertical": prod.vertical_slug,
        "price_display": prod.price_display,
        "categories": parent["categories"],
        "district": parent["district"],
        "state": parent["state"],
        "covered_pincodes": parent["covered_pincodes"],
        "verified": parent["verified"],
        "_geo": parent["_geo"],
    }


async def business_event_payload(session: AsyncSession, business_id: uuid.UUID) -> dict[str, Any]:
    """Fat event payload for business.* events - always carries doc_id, even
    when snapshot is null (the indexer needs the id to delete the doc)."""
    return {
        "doc_id": f"business_{business_id.hex}",
        "business_id": str(business_id),
        "snapshot": await business_snapshot(session, business_id),
    }


async def product_event_payload(session: AsyncSession, product_id: uuid.UUID) -> dict[str, Any]:
    """Fat event payload for product.* events - always carries doc_id, even
    when snapshot is null (the indexer needs the id to delete the doc).

    Callers may pass the id of a row that is invisible-but-real (soft-deleted,
    pending, suspended parent, ...) - e.g. the D19 full-reindex script walks
    every product id including soft-deleted ones so the worker can tombstone
    them. `include_deleted=True` here mirrors the `product_snapshot`/
    `business_snapshot` visibility check, which already treats a soft-deleted
    row as present-but-not-visible rather than absent; the assert below is
    only for a truly nonexistent id, which callers should never pass."""
    snap = await product_snapshot(session, product_id)
    prod = await session.get(Product, product_id, execution_options={"include_deleted": True})
    assert prod is not None
    return {
        "doc_id": f"product_{product_id.hex}",
        "product_id": str(product_id),
        "business_id": str(prod.business_id),
        "snapshot": snap,
    }
