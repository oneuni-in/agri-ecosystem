"""D17 migration: catalog tables exist in schema directory, milk vertical +
schema v1 seeded, spec_schemas is append-only for app_rt (grant-level),
products/registry stay fully mutable for app_rt."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_catalog_tables_exist(db_session: AsyncSession) -> None:
    tables = set(
        (
            await db_session.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'directory'")
            )
        )
        .scalars()
        .all()
    )
    assert {"vertical_registry", "spec_schemas", "products"} <= tables


async def test_milk_vertical_seeded_active(db_session: AsyncSession) -> None:
    row = (
        await db_session.execute(
            text(
                "SELECT slug, status, engines_enabled->>'catalog' AS catalog "
                "FROM directory.vertical_registry WHERE slug = 'milk'"
            )
        )
    ).one()
    assert (row.slug, row.status, row.catalog) == ("milk", "active", "true")


async def test_milk_schema_v1_seeded(db_session: AsyncSession) -> None:
    # M1 (0029) appended a v2 schema row - spec_schemas is append-only, so v1
    # must still be present and unchanged; scope the query to it explicitly.
    row = (
        await db_session.execute(
            text(
                "SELECT version, jsonb_array_length(fields) AS n "
                "FROM directory.spec_schemas WHERE vertical_slug = 'milk' AND version = 1"
            )
        )
    ).one()
    assert (row.version, row.n) == (1, 3)


async def test_schema_admin_flag_seeded_disabled(db_session: AsyncSession) -> None:
    enabled = await db_session.scalar(
        text("SELECT enabled FROM public.feature_flags WHERE key = 'catalog_schema_admin'")
    )
    assert enabled is False


async def test_app_rt_cannot_mutate_spec_schemas(db_session: AsyncSession) -> None:
    # db_session connects as app_rt: INSERT allowed, UPDATE/DELETE revoked
    await db_session.execute(
        text(
            "INSERT INTO directory.spec_schemas (id, vertical_slug, version, fields) "
            "VALUES (gen_random_uuid(), 'milk', 99, '[]'::jsonb)"
        )
    )
    with pytest.raises(Exception):  # noqa: B017 - InsufficientPrivilege wrapping varies
        await db_session.execute(
            text("UPDATE directory.spec_schemas SET version = 100 WHERE version = 99")
        )


async def test_app_rt_full_dml_on_products(db_session: AsyncSession) -> None:
    business_id = await db_session.scalar(
        text(
            "INSERT INTO directory.businesses (id, name, slug, type, primary_pincode) "
            "VALUES (gen_random_uuid(), 'P', 'prod-dml', 'vendor', '641001') RETURNING id"
        )
    )
    await db_session.execute(
        text(
            "INSERT INTO directory.products (id, business_id, vertical_slug, schema_version, "
            "name, slug, specs) VALUES (gen_random_uuid(), :b, 'milk', 1, 'X', 'x-dml', "
            "'{}'::jsonb)"
        ),
        {"b": business_id},
    )
    row = (
        await db_session.execute(
            text("SELECT status, moderation_status FROM directory.products WHERE slug = 'x-dml'")
        )
    ).one()
    assert (row.status, row.moderation_status) == ("active", "pending")
    await db_session.execute(text("DELETE FROM directory.products WHERE slug = 'x-dml'"))
