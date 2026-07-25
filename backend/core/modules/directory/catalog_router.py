"""Catalog API (D17): owner-scoped product writes, plus the public reads that
back SSR product/vertical pages (declared in backend/core/public_routes.txt).
Principal resolution reads request.state.principal directly (populated by
require_auth via shared.security) - the independence contract forbids
modules.directory -> modules.identity. Never log request bodies or query
strings: this module carries business contact PII (phones, addresses)."""

import uuid
from typing import Annotated

import uuid6
from fastapi import Depends, File, HTTPException, Path, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service, search_sync
from modules.directory import milk_home as milk_home_module
from modules.directory.catalog_models import Product, Vertical
from modules.directory.catalog_schemas import (
    ProductCreateIn,
    ProductDetailOut,
    ProductOut,
    ProductPageOut,
    ProductPatchIn,
    PublicProductOut,
    PublicProductPageOut,
    SchemaVersionOut,
    VerticalOut,
    VerticalPageOut,
    media_url,
)
from modules.directory.milk_home_schemas import MilkHomeOut, milk_home_out
from modules.directory.models import Business
from modules.directory.service import BusinessNotFoundError
from modules.directory.specs import SpecValidationError
from shared import media, storage
from shared.db import get_session
from shared.events import publish
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

router = SecureRouter(prefix="/catalog", tags=["catalog"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

EVENT_STREAM = "directory"


async def _publish_best_effort(event_type: str, payload: dict[str, object]) -> None:
    try:
        await publish(EVENT_STREAM, event_type, payload)
    except Exception:  # a Redis blip must never roll back a catalog write
        logger.warning(
            "catalog: event publish failed", extra={"extra_fields": {"event_type": event_type}}
        )


PRODUCT_MEDIA_PREFIX = "products/"

# Best-effort, once-per-process: set on the first upload attempt regardless
# of whether shared.storage.ensure_prefix_public_read actually succeeded
# (it is itself best-effort - see that function's docstring).
_media_prefix_ready = False


async def _ensure_public_media() -> None:
    global _media_prefix_ready
    if _media_prefix_ready:
        return
    await storage.ensure_prefix_public_read(PRODUCT_MEDIA_PREFIX)
    _media_prefix_ready = True


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
    # capture EVERYTHING needed after commit BEFORE committing - ORM
    # attributes expire at commit and async lazy-refresh raises
    payload = await search_sync.product_event_payload(session, product.id)
    out = _product_out(product)
    await session.commit()  # commit BEFORE announcing (admin_router precedent)
    await _publish_best_effort("product.created", payload)
    return out


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
    except catalog_service.SchemaNotFoundError as exc:
        raise HTTPException(status_code=409, detail="no_schema") from exc
    except SpecValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "field": exc.field}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # capture EVERYTHING needed after commit BEFORE committing - ORM
    # attributes expire at commit and async lazy-refresh raises. `status` is
    # a mutable patch field ("active"/"archived"), and business_snapshot's
    # `sites` is partly computed from the business's own approved+active
    # products (mirror of the approve/reject fix in catalog_admin_router.py,
    # D19 review finding 2 owner-facing twin) - an owner archiving/
    # unarchiving their last/first product in a vertical must republish the
    # BUSINESS too, or it never leaves/enters that vertical's site.
    payload = await search_sync.product_event_payload(session, product.id)
    business_payload = await search_sync.business_event_payload(session, product.business_id)
    out = _product_out(product)
    await session.commit()
    await _publish_best_effort("product.updated", payload)
    await _publish_best_effort("business.updated", business_payload)
    return out


@router.post("/products/{product_id}/images", status_code=201)
async def upload_product_image(
    request: Request,
    product_id: uuid.UUID,
    session: SessionDep,
    file: Annotated[UploadFile, File(description="product image (jpeg/png/webp, <=5MiB)")],
) -> ProductOut:
    data = await file.read(media.MAX_IMAGE_BYTES + 1)
    try:
        jpeg, _ = media.reencode_image(data)  # THE shared helper - EXIF gone by construction
    except media.MediaError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    key = f"{PRODUCT_MEDIA_PREFIX}{uuid6.uuid7().hex}.jpg"
    await _ensure_public_media()  # once-per-process, best-effort
    try:
        await storage.put_object(key, jpeg, "image/jpeg")  # storage before DB (avatar precedent)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    try:
        product = await catalog_service.add_product_image(
            session, owner_user_id=_principal_user_id(request), product_id=product_id, key=key
        )
    except catalog_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc
    except ValueError as exc:  # image cap
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _product_out(product)


@router.delete("/products/{product_id}/images/{index}")
async def delete_product_image(
    request: Request, product_id: uuid.UUID, index: int, session: SessionDep
) -> ProductOut:
    try:
        product = await catalog_service.remove_product_image(
            session, owner_user_id=_principal_user_id(request), product_id=product_id, index=index
        )
    except catalog_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc
    except ValueError as exc:  # index out of range
        raise HTTPException(status_code=404, detail="Image not found") from exc
    return _product_out(product)


@router.get("/verticals/{vertical}/schema")
async def get_vertical_schema(
    request: Request, vertical: str, session: SessionDep
) -> SchemaVersionOut:
    """Active field definitions for a vertical (D26 products console) - the
    create form's source of truth. Authed, NOT public: vendors are logged in
    to reach the products console, and keeping this private avoids widening
    the anonymous surface for no reason."""
    found = await catalog_service.get_vertical(session, vertical)
    if found is None or found.status != "active":
        raise HTTPException(status_code=404, detail="Vertical not found")
    schema = await catalog_service.active_schema(session, vertical)
    if schema is None:
        raise HTTPException(status_code=404, detail="Vertical not found")
    return SchemaVersionOut(
        vertical_slug=schema.vertical_slug,
        version=schema.version,
        fields=schema.fields,
        created_at=schema.created_at,
    )


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


@router.get("/milk/home/{pincode}", public=True)
async def milk_home(
    pincode: Annotated[str, Path(pattern=r"^\d{6}$")],
    session: SessionDep,
    type: str | None = None,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> MilkHomeOut:
    """Pincode-first milk blend (D23): vendors + brands + schema-driven
    filters + computed price banner, with a 3-way empty-state scope.
    Public + keyset-only + rate-limited (pincode-enumeration defence)."""
    try:
        result = await milk_home_module.milk_home(
            session, pincode=pincode, milk_type=type, cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return milk_home_out(pincode, result)
