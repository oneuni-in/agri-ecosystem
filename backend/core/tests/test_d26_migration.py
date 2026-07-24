"""D26 schema: tier-intent + delivery-window columns, append-only
profile_views (grant-enforced: app_rt gets SELECT+INSERT only)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_business_columns_added(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'directory' AND table_name = 'businesses' "
                "AND column_name IN ('premium_requested_at', 'delivery_windows')"
            )
        )
    ).all()
    found = {row.column_name: row.is_nullable for row in rows}
    assert found == {"premium_requested_at": "YES", "delivery_windows": "YES"}


async def test_profile_views_table_and_dedupe_index(db_session: AsyncSession) -> None:
    columns = {
        row.column_name
        for row in (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'directory' AND table_name = 'profile_views'"
                )
            )
        ).all()
    }
    assert columns == {"id", "business_id", "pincode", "viewer_hash", "occurred_at"}
    indexes = {
        row.indexname
        for row in (
            await db_session.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'directory' AND tablename = 'profile_views'"
                )
            )
        ).all()
    }
    assert "uq_directory_profile_views_dedupe" in indexes


async def test_profile_views_append_only_grant(db_session: AsyncSession) -> None:
    grants = {
        row.privilege_type
        for row in (
            await db_session.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_schema = 'directory' AND table_name = 'profile_views' "
                    "AND grantee = 'app_rt'"
                )
            )
        ).all()
    }
    assert grants == {"SELECT", "INSERT"}
