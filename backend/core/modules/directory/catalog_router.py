"""Catalog API (D17): owner-scoped product writes, plus the public reads that
back SSR product/vertical pages (declared in backend/core/public_routes.txt).
Principal resolution reads request.state.principal directly (populated by
require_auth via shared.security) - the independence contract forbids
modules.directory -> modules.identity. Never log request bodies or query
strings: this module carries business contact PII (phones, addresses)."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service
from modules.directory.catalog_models import Product, Vertical
from modules.directory.catalog_schemas import (
    ProductCreateIn,
    ProductDetailOut,
    ProductOut,
    ProductPageOut,
    ProductPatchIn,
    PublicProductOut,
    PublicProductPageOut,
    VerticalOut,
    VerticalPageOut,
    media_url,
)
from modules.directory.models import Business
from modules.directory.service import BusinessNotFoundError
from modules.directory.specs import SpecValidationError
from shared.db import get_session
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError
from shared.security import SecureRouter

router = SecureRouter(prefix="/catalog", tags=["catalog"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal  # set by require_auth (shared.security)
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)  # narrow Starlette state's Any for mypy
    return user_id


def _product_out(product: Product) -> ProductOut:
    return ProductOut(
        id=product.id,
        business_id=product.business_id,
        vertical_slug=product.vertical_slug,
        schema_version=product.schema_version,
        name=product.name,
        slug=product.slug,
        specs=product.specs,
        price_display=product.price_display,
        status=product.status,
        moderation_status=product.moderation_status,
        images=[media_url(key) for key in product.media_keys],
        created_at=product.created_at,
    )


def _public_product_out(product: Product, business: Business) -> PublicProductOut:
    return PublicProductOut(
        id=product.id,
        business_id=product.business_id,
        business_name=business.name,
        business_slug=business.slug,
        vertical_slug=product.vertical_slug,
        schema_version=product.schema_version,
        name=product.name,
        slug=product.slug,
        specs=product.specs,
        price_display=product.price_display,
        status=product.status,
        images=[media_url(key) for key in product.media_keys],
        created_at=product.created_at,
    )


async def _business_by_slug(session: AsyncSession, slug: str) -> Business | None:
    business = await session.scalar(
        select(Business).where(Business.slug == slug, Business.status == "active")
    )
    return business


async def _businesses_by_id(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, Business]:
    if not ids:
        return {}
    rows = await session.scalars(select(Business).where(Business.id.in_(ids)))
    return {b.id: b for b in rows.all()}


def _vertical_out(vertical: Vertical) -> VerticalOut:
    return VerticalOut(
        slug=vertical.slug,
        name=vertical.name.to_dict(),
        engines_enabled=vertical.engines_enabled,
        nav_placement=vertical.nav_placement,
    )


@router.post("/businesses/{business_id}/products", status_code=201)
async def create_product(
    request: Request, business_id: uuid.UUID, body: ProductCreateIn, session: SessionDep
) -> ProductOut:
    try:
        product = await catalog_service.create_product(
            session,
            owner_user_id=_principal_user_id(request),
            business_id=business_id,
            vertical_slug=body.vertical_slug,
            name=body.name,
            specs=body.specs,
            price_display=body.price_display,
        )
    except BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    except catalog_service.VerticalNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Vertical not found") from exc
    except catalog_service.SchemaNotFoundError as exc:
        raise HTTPException(status_code=409, detail="no_schema") from exc
    except SpecValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "field": exc.field}) from exc
    return _product_out(product)


@router.get("/my/products")
async def list_my_products(
    request: Request,
    business_id: uuid.UUID,
    session: SessionDep,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> ProductPageOut:
    try:
        page = await catalog_service.list_my_products(
            session, _principal_user_id(request), business_id, cursor=cursor, limit=limit
        )
    except BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return ProductPageOut(items=[_product_out(p) for p in page.items], next_cursor=page.next_cursor)


@router.patch("/products/{product_id}")
async def update_product(
    request: Request, product_id: uuid.UUID, body: ProductPatchIn, session: SessionDep
) -> ProductOut:
    try:
        product = await catalog_service.update_product(
            session,
            owner_user_id=_principal_user_id(request),
            product_id=product_id,
            patch=body.model_dump(exclude_unset=True),
        )
    except catalog_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc
    except SpecValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "field": exc.field}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _product_out(product)


# --- public reads (declared in backend/core/public_routes.txt) -------------


@router.get("/verticals", public=True)
async def list_verticals(
    session: SessionDep, cursor: str | None = None, limit: LimitQuery = DEFAULT_PAGE_SIZE
) -> VerticalPageOut:
    """Active verticals - SSR nav source (Milk.in D23 and siblings)."""
    try:
        page = await catalog_service.list_verticals(session, cursor=cursor, limit=limit)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return VerticalPageOut(
        items=[_vertical_out(v) for v in page.items], next_cursor=page.next_cursor
    )


@router.get("/products/{slug}", public=True)
async def get_product_detail(slug: str, session: SessionDep) -> ProductDetailOut:
    """Public product page (SSR source for Milk.in D23). Pending/archived/
    suspended-business -> the same 404. Renders with the PINNED schema
    version - never the active one (old products must keep rendering)."""
    result = await catalog_service.get_public_product(session, slug)
    if result is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product, business = result
    schema = await catalog_service.get_schema(
        session, product.vertical_slug, product.schema_version
    )
    return ProductDetailOut(
        product=_public_product_out(product, business),
        schema_fields=schema.fields if schema else [],
    )


@router.get("/businesses/{slug}/products", public=True)
async def list_business_products(
    slug: str, session: SessionDep, cursor: str | None = None, limit: LimitQuery = DEFAULT_PAGE_SIZE
) -> PublicProductPageOut:
    """Approved+active products for a business's public storefront section.
    Unknown/inactive business -> an empty page (same as covers_search's
    no-match shape), not a 404 - the slug may simply have no catalog yet."""
    try:
        page = await catalog_service.list_business_products(
            session, slug, cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    if not page.items:
        return PublicProductPageOut(items=[], next_cursor=page.next_cursor)
    business = await _business_by_slug(session, slug)
    assert business is not None  # page.items non-empty implies the service found it active
    return PublicProductPageOut(
        items=[_public_product_out(p, business) for p in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/verticals/{vertical}/products", public=True)
async def list_vertical_products(
    vertical: str,
    session: SessionDep,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> PublicProductPageOut:
    """Approved+active products across all businesses in a vertical."""
    try:
        page = await catalog_service.list_vertical_products(
            session, vertical, cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    businesses = await _businesses_by_id(session, [p.business_id for p in page.items])
    return PublicProductPageOut(
        items=[_public_product_out(p, businesses[p.business_id]) for p in page.items],
        next_cursor=page.next_cursor,
    )
