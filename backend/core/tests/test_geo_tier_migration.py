"""M4 schema: geo.pincode_tiers + append-only history + ads tier column."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


async def _columns(db_session: AsyncSession, schema: str, table: str) -> set[str]:
    rows = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=:s AND table_name=:t"
        ),
        {"s": schema, "t": table},
    )
    return {r[0] for r in rows}


async def test_pincode_tiers_columns(db_session: AsyncSession) -> None:
    cols = await _columns(db_session, "geo", "pincode_tiers")
    assert {
        "pincode",
        "population",
        "population_grade",
        "tier",
        "user_count",
        "computed_at",
        "tier_changed_at",
        "method",
    } <= cols


async def test_pincode_tier_history_columns(db_session: AsyncSession) -> None:
    cols = await _columns(db_session, "geo", "pincode_tier_history")
    assert {"pincode", "old_tier", "new_tier", "old_method", "new_method", "reason"} <= cols
    assert "updated_at" not in cols  # immutable table: created_at only


async def test_tier_bounds_enforced(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text(
                "INSERT INTO geo.pincode_tiers (id, created_at, updated_at, pincode,"
                " population, population_grade, tier, user_count, method)"
                " VALUES (gen_random_uuid(), now(), now(), '999999', 10, 'town', 6, 0,"
                " 'population')"
            )
        )


async def test_history_is_append_only(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            "INSERT INTO geo.pincode_tier_history (id, created_at, pincode, old_tier,"
            " new_tier, old_method, new_method, reason)"
            " VALUES (gen_random_uuid(), now(), '641001', NULL, 2, NULL, 'population',"
            " 'initial')"
        )
    )
    with pytest.raises(DBAPIError):
        await db_session.execute(text("UPDATE geo.pincode_tier_history SET new_tier = 1"))


async def test_delivery_decisions_gained_tier(db_session: AsyncSession) -> None:
    cols = await _columns(db_session, "ads", "delivery_decisions")
    assert "tier" in cols


def test_pincode_tier_settings_defaults() -> None:
    from settings import get_settings

    s = get_settings()
    assert s.pincode_tier_percentiles == "99,90,60,25"
    assert s.pincode_tier_user_threshold == 100
    assert s.pincode_tier_promote_only is True
    assert s.geo_tier_job_enabled is True
