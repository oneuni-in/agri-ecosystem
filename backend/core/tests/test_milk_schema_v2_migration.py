"""Milk spec-schema v2 (M1): the 13-value dairy taxonomy as config, plus the
backfill that moves already-seeded products onto it."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service
from modules.directory.specs import parse_fields

pytestmark = pytest.mark.asyncio

EXPECTED_CATEGORIES = [
    "milk",
    "ghee",
    "paneer",
    "milk-powder",
    "yogurt",
    "lassi",
    "curd",
    "buttermilk",
    "cheese",
    "butter",
    "cream",
    "khoa",
    "flavoured-milk",
]


async def test_active_milk_schema_is_v2(db_session: AsyncSession) -> None:
    schema = await catalog_service.active_schema(db_session, "milk")
    assert schema is not None
    assert schema.version == 2


async def test_category_field_carries_all_values_with_full_i18n(
    db_session: AsyncSession,
) -> None:
    schema = await catalog_service.active_schema(db_session, "milk")
    assert schema is not None
    fields = {f.key: f for f in parse_fields(schema.fields)}
    category = fields["category"]
    assert category.options == EXPECTED_CATEGORIES
    assert category.required is True
    assert category.filterable is True and category.facet is True
    assert category.option_meta is not None
    for value in EXPECTED_CATEGORIES:
        meta = category.option_meta[value]
        # i18n-gap threat: no value may ship English-only
        assert set(meta.label) == {"en", "ta", "hi"}
        assert all(meta.label[loc].strip() for loc in ("en", "ta", "hi"))
        assert meta.icon


async def test_milk_type_is_optional_in_v2_and_gained_mixed(
    db_session: AsyncSession,
) -> None:
    schema = await catalog_service.active_schema(db_session, "milk")
    assert schema is not None
    fields = {f.key: f for f in parse_fields(schema.fields)}
    milk_type = fields["milk_type"]
    assert milk_type.required is False  # a ghee product has no milk type
    # options are APPEND-ONLY: every v1 value must survive
    assert milk_type.options is not None
    for legacy in ("cow", "buffalo", "a2", "toned", "organic"):
        assert legacy in milk_type.options
    assert "mixed" in milk_type.options


async def test_v1_is_still_readable(db_session: AsyncSession) -> None:
    """Products pinned at v1 must keep rendering - versions are immutable."""
    v1 = await catalog_service.get_schema(db_session, "milk", 1)
    assert v1 is not None
    assert {f.key for f in parse_fields(v1.fields)} == {"milk_type", "fat_percent", "pack_size"}


async def test_backfill_left_no_uncategorised_milk_product(
    db_session: AsyncSession,
) -> None:
    stranded = await db_session.scalar(
        text(
            "SELECT count(*) FROM directory.products "
            "WHERE vertical_slug = 'milk' AND specs->>'category' IS NULL"
        )
    )
    assert stranded == 0


async def test_backfilled_products_are_repinned_to_v2(
    db_session: AsyncSession,
) -> None:
    stale = await db_session.scalar(
        text(
            "SELECT count(*) FROM directory.products "
            "WHERE vertical_slug = 'milk' AND specs->>'category' = 'milk' "
            "AND schema_version <> 2"
        )
    )
    assert stale == 0


async def test_backfilled_specs_still_validate_against_v2(
    db_session: AsyncSession,
) -> None:
    """A backfilled row must satisfy the version it is now pinned to."""
    from modules.directory.specs import validate_specs

    schema = await catalog_service.active_schema(db_session, "milk")
    assert schema is not None
    fields = parse_fields(schema.fields)
    rows = (
        await db_session.execute(
            text("SELECT specs FROM directory.products WHERE vertical_slug = 'milk' LIMIT 50")
        )
    ).all()
    for (specs,) in rows:
        validate_specs(specs, fields)  # raises on any violation


async def test_spec_schemas_remain_append_only(db_session: AsyncSession) -> None:
    """0018 revoked UPDATE/DELETE from app_rt; 0029 must not have restored it."""
    granted = await db_session.scalar(
        text(
            "SELECT count(*) FROM information_schema.role_table_grants "
            "WHERE table_schema = 'directory' AND table_name = 'spec_schemas' "
            "AND grantee = 'app_rt' AND privilege_type IN ('UPDATE', 'DELETE')"
        )
    )
    assert granted == 0
