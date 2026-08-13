"""Catalog service (D17): vertical registry reads, append-only schema
versions, schema-validated products. Writes are owner-scoped through
modules.directory.service.get_owned_business (same-module import - this is
WHY catalog lives in the directory module)."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.catalog_models import Product, SpecSchema, Vertical
from modules.directory.models import Business
from modules.directory.service import BusinessNotFoundError, _slugify, get_owned_business
from modules.directory.specs import parse_fields, validate_specs
from shared.db import soft_delete
from shared.pagination import DEFAULT_PAGE_SIZE, Page, paginate

PRODUCT_MUTABLE_FIELDS = {"name", "specs", "price_display", "status"}
MAX_PRODUCT_IMAGES = 8


class VerticalNotFoundError(Exception):
    """Unknown or hidden vertical."""


class SchemaNotFoundError(Exception):
    """Vertical has no schema version yet - products cannot be created."""


class ProductNotFoundError(Exception):
    """No such product - or its business isn't yours. Router 404s both identically."""


async def list_verticals(
    session: AsyncSession, *, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
) -> Page[Vertical]:
    return await paginate(
        session, select(Vertical).where(Vertical.status == "active"), cursor=cursor, limit=limit
    )


async def get_vertical(session: AsyncSession, slug: str) -> Vertical | None:
    vertical = await session.scalar(select(Vertical).where(Vertical.slug == slug))
    return vertical


async def active_schema(session: AsyncSession, vertical_slug: str) -> SpecSchema | None:
    schema = await session.scalar(
        select(SpecSchema)
        .where(SpecSchema.vertical_slug == vertical_slug)
        .order_by(SpecSchema.version.desc())
        .limit(1)
    )
    return schema


async def get_schema(session: AsyncSession, vertical_slug: str, version: int) -> SpecSchema | None:
    schema = await session.scalar(
        select(SpecSchema).where(
            SpecSchema.vertical_slug == vertical_slug, SpecSchema.version == version
        )
    )
    return schema


async def list_schema_versions(session: AsyncSession, vertical_slug: str) -> list[SpecSchema]:
    rows = await session.scalars(
        select(SpecSchema)
        .where(SpecSchema.vertical_slug == vertical_slug)
        .order_by(SpecSchema.version)
    )
    return list(rows.all())


async def create_schema_version(
    session: AsyncSession, *, vertical_slug: str, fields_raw: object
) -> SpecSchema:
    """Append the next version. parse_fields raises SpecValidationError on a
    malformed definition; versions are immutable once created (grant-enforced)."""
    if await get_vertical(session, vertical_slug) is None:
        raise VerticalNotFoundError(vertical_slug)
    fields = parse_fields(fields_raw)
    current = await session.scalar(
        select(func.max(SpecSchema.version)).where(SpecSchema.vertical_slug == vertical_slug)
    )
    schema = SpecSchema(
        vertical_slug=vertical_slug,
        version=(current or 0) + 1,
        fields=[f.model_dump(exclude_none=True) for f in fields],
    )
    session.add(schema)
    await session.flush()
    return schema


async def _free_product_slug(session: AsyncSession, base: str) -> str:
    candidate, n = base, 1
    while (
        await session.scalar(
            select(Product.id)
            .where(Product.slug == candidate)
            # soft-deleted rows still hold their unique slug
            .execution_options(include_deleted=True)
        )
        is not None
    ):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


async def _build_product(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    vertical_slug: str,
    name: str,
    specs: dict[str, Any],
    price_display: str | None = None,
) -> Product:
    """Shared post-authorization product construction: create_product (owner
    API) and seed_import (D27 ownerless seed) both build products through
    this one path so spec pinning/validation can never diverge."""
    vertical = await get_vertical(session, vertical_slug)
    if vertical is None or vertical.status != "active":
        raise VerticalNotFoundError(vertical_slug)
    schema = await active_schema(session, vertical_slug)
    if schema is None:
        raise SchemaNotFoundError(vertical_slug)
    validated = validate_specs(specs, parse_fields(schema.fields))
    product = Product(
        business_id=business_id,
        vertical_slug=vertical_slug,
        schema_version=schema.version,  # pinned at write time (NN#1)
        name=name,
        slug=await _free_product_slug(session, _slugify(name)),
        specs=validated,
        price_display=price_display,
    )
    session.add(product)
    await session.flush()
    await session.refresh(product)  # server defaults: status, moderation_status
    return product


async def create_product(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    vertical_slug: str,
    name: str,
    specs: dict[str, Any],
    price_display: str | None = None,
) -> Product:
    await get_owned_business(session, owner_user_id, business_id)  # IDOR gate
    return await _build_product(
        session,
        business_id=business_id,
        vertical_slug=vertical_slug,
        name=name,
        specs=specs,
        price_display=price_display,
    )


async def get_owned_product(
    session: AsyncSession, owner_user_id: uuid.UUID, product_id: uuid.UUID
) -> Product:
    """Parent-ownership gate (update_branch precedent): missing product and
    not-your-business both collapse to ProductNotFoundError so callers - and
    the router's 404 mapping - only ever see one exception."""
    product = await session.scalar(select(Product).where(Product.id == product_id))
    if product is None:
        raise ProductNotFoundError(str(product_id))
    try:
        await get_owned_business(session, owner_user_id, product.business_id)
    except BusinessNotFoundError as exc:
        raise ProductNotFoundError(str(product_id)) from exc
    return product


async def update_product(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    product_id: uuid.UUID,
    patch: dict[str, Any],
) -> Product:
    unknown = set(patch) - PRODUCT_MUTABLE_FIELDS
    if unknown:
        raise ValueError(f"immutable or unknown fields: {sorted(unknown)}")
    product = await get_owned_product(session, owner_user_id, product_id)
    if "status" in patch and patch["status"] not in ("active", "archived"):
        raise ValueError(f"invalid product status: {patch['status']!r}")
    if "name" in patch and patch["name"] is None:
        raise ValueError("name cannot be null")
    if "specs" in patch:
        # a write opts into the current contract; untouched products keep
        # their old pin (the version-pinning contract, NN#1)
        schema = await active_schema(session, product.vertical_slug)
        if schema is None:
            raise SchemaNotFoundError(product.vertical_slug)
        raw_specs = patch.pop("specs")
        product.specs = validate_specs(raw_specs, parse_fields(schema.fields))
        product.schema_version = schema.version
    for field, value in patch.items():
        setattr(product, field, value)
    await session.flush()
    return product


async def list_my_products(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[Product]:
    await get_owned_business(session, owner_user_id, business_id)  # IDOR gate
    return await paginate(
        session,
        select(Product).where(Product.business_id == business_id),
        cursor=cursor,
        limit=limit,
    )


async def add_product_image(
    session: AsyncSession, *, owner_user_id: uuid.UUID, product_id: uuid.UUID, key: str
) -> Product:
    product = await get_owned_product(session, owner_user_id, product_id)
    if len(product.media_keys) >= MAX_PRODUCT_IMAGES:
        raise ValueError(f"product already has {MAX_PRODUCT_IMAGES} images (cap)")
    # JSONB in-place mutation isn't change-tracked - assign a new list.
    product.media_keys = [*product.media_keys, key]
    await session.flush()
    return product


async def remove_product_image(
    session: AsyncSession, *, owner_user_id: uuid.UUID, product_id: uuid.UUID, index: int
) -> Product:
    product = await get_owned_product(session, owner_user_id, product_id)
    if index < 0 or index >= len(product.media_keys):
        raise ValueError(f"image index out of range: {index}")
    updated = list(product.media_keys)
    del updated[index]
    product.media_keys = updated
    await session.flush()
    return product


async def delete_product(
    session: AsyncSession, *, owner_user_id: uuid.UUID, product_id: uuid.UUID
) -> Product:
    """Owner removal (U2 Group B) — a SOFT delete, never a hard DELETE. The
    default ORM filter hides the row everywhere public immediately; support
    can restore by clearing `deleted_at`. Funnels through get_owned_product,
    so not-yours and missing both collapse to ProductNotFoundError → 404."""
    product = await get_owned_product(session, owner_user_id, product_id)
    soft_delete(product)
    await session.flush()
    return product


async def get_public_product(session: AsyncSession, slug: str) -> tuple[Product, Business] | None:
    row = (
        await session.execute(
            select(Product, Business)
            .join(Business, Business.id == Product.business_id)
            .where(
                Product.slug == slug,
                Product.moderation_status == "approved",
                Product.status == "active",
                Business.status == "active",
            )
        )
    ).first()
    if row is None:
        return None
    return row[0], row[1]


async def list_business_products(
    session: AsyncSession,
    business_slug: str,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[Product]:
    business = await session.scalar(
        select(Business).where(Business.slug == business_slug, Business.status == "active")
    )
    if business is None:
        return Page(items=[], next_cursor=None)
    return await paginate(
        session,
        select(Product).where(
            Product.business_id == business.id,
            Product.moderation_status == "approved",
            Product.status == "active",
        ),
        cursor=cursor,
        limit=limit,
    )


async def list_vertical_products(
    session: AsyncSession,
    vertical_slug: str,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[Product]:
    vertical = await get_vertical(session, vertical_slug)
    if vertical is None or vertical.status != "active":
        return Page(items=[], next_cursor=None)
    return await paginate(
        session,
        select(Product)
        .join(Business, Business.id == Product.business_id)
        .where(
            Product.vertical_slug == vertical_slug,
            Product.moderation_status == "approved",
            Product.status == "active",
            Business.status == "active",
        ),
        cursor=cursor,
        limit=limit,
    )


async def list_products_for_moderation(
    session: AsyncSession, *, status: str, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
) -> Page[Product]:
    return await paginate(
        session,
        select(Product).where(Product.moderation_status == status),
        cursor=cursor,
        limit=limit,
    )


async def moderate_product(
    session: AsyncSession, *, product_id: uuid.UUID, approve: bool
) -> Product:
    """Idempotent single-column flip - no FOR-UPDATE dance needed (unlike
    claim approval's multi-row choreography)."""
    product = await session.scalar(select(Product).where(Product.id == product_id))
    if product is None:
        raise ProductNotFoundError(str(product_id))
    product.moderation_status = "approved" if approve else "rejected"
    await session.flush()
    return product
