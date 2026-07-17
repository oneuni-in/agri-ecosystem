"""Catalog service (D17): vertical registry reads, append-only schema
versions, schema-validated products. Writes are owner-scoped through
modules.directory.service.get_owned_business (same-module import - this is
WHY catalog lives in the directory module)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.catalog_models import SpecSchema, Vertical
from modules.directory.specs import parse_fields
from shared.pagination import DEFAULT_PAGE_SIZE, Page, paginate


class VerticalNotFoundError(Exception):
    """Unknown or hidden vertical."""


class SchemaNotFoundError(Exception):
    """Vertical has no schema version yet - products cannot be created."""


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
