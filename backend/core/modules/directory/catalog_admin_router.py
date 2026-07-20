"""Catalog admin surface (D17 Task 7): flag-gated schema version CRUD +
product moderation.

Auth is ROLE-gated, not permission-gated: modules.directory must never import
modules.identity (import-linter independence), so require_permission is
unavailable here - same trade-off as modules/directory/admin_router.py and
modules/coins/admin_router.py.

Schema versions are append-only (immutable once published, DB-grant
enforced): a version-create is a race between admins publishing
concurrently, hardened with a savepoint + IntegrityError->409 mapping
(claims.submit_claim precedent) rather than trusting the max-version read
alone. Every decision writes an audit entry IN the caller's transaction
(D12). Product approval additionally publishes a post-commit, best-effort
product.updated search snapshot event (D19 Task 1) - schema version writes
still publish nothing. Never log request bodies or query strings."""

import uuid
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service, search_sync
from modules.directory.catalog_models import Product, SpecSchema
from modules.directory.catalog_schemas import (
    ProductOut,
    ProductPageOut,
    ProductRejectIn,
    SchemaCreateIn,
    SchemaVersionListOut,
    SchemaVersionOut,
    media_url,
)
from modules.directory.specs import SpecValidationError
from shared.audit import audit
from shared.db import get_session
from shared.events import publish
from shared.flags import flag_enabled
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

admin_router = SecureRouter(prefix="/admin/catalog", tags=["catalog-admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]
StatusQuery = Literal["pending", "approved", "rejected"]

EVENT_STREAM = "directory"
STAFF = "staff"
SUPER_ADMIN = "super_admin"


async def _publish_best_effort(event_type: str, payload: dict[str, object]) -> None:
    try:
        await publish(EVENT_STREAM, event_type, payload)
    except Exception:  # a Redis blip must never roll back an admin decision
        logger.warning(
            "catalog admin: event publish failed",
            extra={"extra_fields": {"event_type": event_type}},
        )


def _require_role(request: Request, *allowed: str) -> uuid.UUID:
    """Fail-closed role gate. Returns the acting admin's user_id (for audit)."""
    principal = request.state.principal
    roles = getattr(principal, "roles", ())
    if not any(role in roles for role in allowed):
        raise HTTPException(status_code=403, detail="missing_role")
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)
    return user_id


def _schema_version_out(schema: SpecSchema) -> SchemaVersionOut:
    return SchemaVersionOut(
        vertical_slug=schema.vertical_slug,
        version=schema.version,
        fields=schema.fields,
        created_at=schema.created_at,
    )


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


@admin_router.get("/schemas/{vertical_slug}")
async def list_schema_versions(
    request: Request, vertical_slug: str, session: SessionDep
) -> SchemaVersionListOut:
    _require_role(request, STAFF, SUPER_ADMIN)
    schemas = await catalog_service.list_schema_versions(session, vertical_slug)
    return SchemaVersionListOut(items=[_schema_version_out(s) for s in schemas])


@admin_router.get("/schemas/{vertical_slug}/{version}")
async def get_schema_version(
    request: Request, vertical_slug: str, version: int, session: SessionDep
) -> SchemaVersionOut:
    _require_role(request, STAFF, SUPER_ADMIN)
    schema = await catalog_service.get_schema(session, vertical_slug, version)
    if schema is None:
        raise HTTPException(status_code=404, detail="Schema version not found")
    return _schema_version_out(schema)


@admin_router.post("/schemas/{vertical_slug}", status_code=201)
async def create_schema_version(
    request: Request, vertical_slug: str, body: SchemaCreateIn, session: SessionDep
) -> SchemaVersionOut:
    # role check FIRST, then flag check (coins admin_router.py precedent)
    admin_id = _require_role(request, SUPER_ADMIN)
    if not await flag_enabled("catalog_schema_admin", session=session):
        raise HTTPException(status_code=403, detail="schema_admin_disabled")
    # Savepoint wraps only the insert so a lost race against the
    # (vertical_slug, version) unique constraint rolls back just this
    # insert, not the caller's transaction (claims.submit_claim precedent).
    sp = await session.begin_nested()
    try:
        schema = await catalog_service.create_schema_version(
            session, vertical_slug=vertical_slug, fields_raw=body.fields
        )
    except catalog_service.VerticalNotFoundError as exc:
        await sp.rollback()
        raise HTTPException(status_code=404, detail="Vertical not found") from exc
    except SpecValidationError as exc:
        await sp.rollback()
        raise HTTPException(status_code=422, detail={"code": exc.code, "field": exc.field}) from exc
    except IntegrityError as exc:  # lost the race to the unique constraint
        await sp.rollback()
        raise HTTPException(status_code=409, detail="version_conflict") from exc
    else:
        await sp.commit()
    await audit(
        session,
        action="catalog.schema_created",
        actor_user_id=admin_id,
        target_type="spec_schema",
        target_id=f"{vertical_slug}:{schema.version}",
        metadata={
            "vertical_slug": vertical_slug,
            "version": schema.version,
            "field_count": len(schema.fields),
        },
        ip=request.client.host if request.client else None,
    )
    return _schema_version_out(schema)


@admin_router.get("/products")
async def list_products_for_moderation(
    request: Request,
    session: SessionDep,
    status: StatusQuery = "pending",
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> ProductPageOut:
    _require_role(request, STAFF, SUPER_ADMIN)
    try:
        page = await catalog_service.list_products_for_moderation(
            session, status=status, cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return ProductPageOut(items=[_product_out(p) for p in page.items], next_cursor=page.next_cursor)


@admin_router.post("/products/{product_id}/approve")
async def approve_product(
    request: Request, product_id: uuid.UUID, session: SessionDep
) -> ProductOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        product = await catalog_service.moderate_product(
            session, product_id=product_id, approve=True
        )
    except catalog_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc
    # audit rides the SAME transaction as the decision (D12 contract)
    await audit(
        session,
        action="catalog.product_approved",
        actor_user_id=admin_id,
        target_type="product",
        target_id=str(product.id),
        metadata={"business_id": str(product.business_id)},
        ip=request.client.host if request.client else None,
    )
    # capture EVERYTHING needed after commit BEFORE committing - ORM
    # attributes expire at commit and async lazy-refresh raises
    payload = await search_sync.product_event_payload(session, product.id)
    out = _product_out(product)
    await session.commit()  # commit BEFORE announcing (admin_router precedent)
    await _publish_best_effort("product.updated", payload)
    return out


@admin_router.post("/products/{product_id}/reject")
async def reject_product(
    request: Request, product_id: uuid.UUID, body: ProductRejectIn, session: SessionDep
) -> ProductOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        product = await catalog_service.moderate_product(
            session, product_id=product_id, approve=False
        )
    except catalog_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc
    await audit(
        session,
        action="catalog.product_rejected",
        actor_user_id=admin_id,
        target_type="product",
        target_id=str(product.id),
        metadata={"business_id": str(product.business_id), "note": body.note},
        ip=request.client.host if request.client else None,
    )
    return _product_out(product)
