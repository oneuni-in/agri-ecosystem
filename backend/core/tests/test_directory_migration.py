"""D15 migration: directory tables exist, categories seeded, constraints and
defaults hold, app_rt can write (mutable owner-scoped data - no triggers)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _insert_business(session: AsyncSession, slug: str) -> uuid.UUID:
    business_id = await session.scalar(
        text(
            "INSERT INTO directory.businesses "
            "(id, owner_user_id, name, slug, type, primary_pincode) VALUES "
            "(gen_random_uuid(), gen_random_uuid(), 'B', :s, 'vendor', '641001') "
            "RETURNING id"
        ),
        {"s": slug},
    )
    assert isinstance(business_id, uuid.UUID)
    return business_id


async def test_directory_tables_exist(db_session: AsyncSession) -> None:
    tables = set(
        (
            await db_session.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'directory'")
            )
        )
        .scalars()
        .all()
    )
    assert {
        "businesses",
        "branches",
        "categories",
        "business_categories",
        "business_coverage",
    } <= tables


async def test_categories_seeded(db_session: AsyncSession) -> None:
    slugs = set(
        (await db_session.execute(text("SELECT slug FROM directory.categories"))).scalars().all()
    )
    assert {"farm", "dairy", "shop", "lab", "nursery", "equipment", "service", "other"} <= slugs


async def test_business_defaults(db_session: AsyncSession) -> None:
    business_id = await _insert_business(db_session, "defaults-test")
    row = (
        await db_session.execute(
            text(
                "SELECT status, verification_status, subscription_tier "
                "FROM directory.businesses WHERE id = :b"
            ),
            {"b": business_id},
        )
    ).one()
    assert (row.status, row.verification_status, row.subscription_tier) == (
        "active",
        "unverified",
        "free",
    )


async def test_business_slug_unique(db_session: AsyncSession) -> None:
    await _insert_business(db_session, "dup-slug")
    await db_session.flush()
    with pytest.raises(Exception):  # noqa: B017 - unique-violation wrapping varies by driver
        await _insert_business(db_session, "dup-slug")
        await db_session.flush()


async def test_coverage_unique_per_business_pincode(db_session: AsyncSession) -> None:
    business_id = await _insert_business(db_session, "coverage-uniq")
    insert = text(
        "INSERT INTO directory.business_coverage (id, business_id, pincode) "
        "VALUES (gen_random_uuid(), :b, '641001')"
    )
    await db_session.execute(insert, {"b": business_id})
    with pytest.raises(Exception):  # noqa: B017 - unique-violation wrapping varies by driver
        await db_session.execute(insert, {"b": business_id})


async def test_app_rt_can_delete_business_rows(db_session: AsyncSession) -> None:
    # db_session connects as app_rt; directory data is mutable (no coins-style
    # immutability trigger), so full DML must work.
    business_id = await _insert_business(db_session, "delete-me")
    await db_session.execute(
        text("DELETE FROM directory.businesses WHERE id = :b"), {"b": business_id}
    )
