# backend/core/tests/test_ads_migration.py
"""D21 ads schema: tables, daily partitions + DEFAULT backstop, and the
append-only guarantee on impressions/clicks (trigger + grant - the raw
click-fraud log can never be rewritten, not even by the owner role)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_ads_tables_exist(db_session: AsyncSession) -> None:
    rows = (
        (
            await db_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'ads' AND table_name IN "
                    "('campaigns','creatives','placements','impressions','clicks') "
                    "ORDER BY table_name"
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows == ["campaigns", "clicks", "creatives", "impressions", "placements"]


async def _insert_impression(session: AsyncSession, occurred_at: datetime) -> uuid.UUID:
    row_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO ads.impressions "
            "(id, placement_id, creative_id, slot_key, viewer_hash, pincode, occurred_at) "
            "VALUES (:id, :p, :c, 'directory_browse', 'vh-test', '641001', :at)"
        ),
        {"id": row_id, "p": uuid.uuid4(), "c": uuid.uuid4(), "at": occurred_at},
    )
    return row_id


async def test_partition_insert_across_day_boundary(db_session: AsyncSession) -> None:
    """NON-NEGOTIABLE 3: an insert at 23:59:59 and one at 00:00:01 the next
    day both succeed and land in DIFFERENT daily partitions."""
    today = datetime.now(UTC).date()
    late = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=UTC)
    early_next = late + timedelta(seconds=2)
    id_late = await _insert_impression(db_session, late)
    id_next = await _insert_impression(db_session, early_next)
    parts = (
        await db_session.execute(
            text("SELECT id, tableoid::regclass::text FROM ads.impressions WHERE id IN (:a, :b)"),
            {"a": id_late, "b": id_next},
        )
    ).all()
    by_id = {row[0]: row[1] for row in parts}
    assert by_id[id_late] == f"ads.impressions_p{today:%Y%m%d}"
    assert by_id[id_next] == f"ads.impressions_p{early_next:%Y%m%d}"
    await db_session.rollback()


async def test_far_future_insert_lands_in_default_partition(db_session: AsyncSession) -> None:
    """The DEFAULT partition is the backstop: even a day with no pre-created
    partition accepts inserts (inserts NEVER fail on a new day)."""
    far = datetime.now(UTC) + timedelta(days=45)
    row_id = await _insert_impression(db_session, far)
    part = await db_session.scalar(
        text("SELECT tableoid::regclass::text FROM ads.impressions WHERE id = :a"),
        {"a": row_id},
    )
    assert part == "ads.impressions_default"
    await db_session.rollback()


async def test_impressions_append_only_for_app_rt(db_session: AsyncSession) -> None:
    """db_session connects as app_rt: INSERT works, UPDATE/DELETE denied by
    grant (0015 precedent)."""
    row_id = await _insert_impression(db_session, datetime.now(UTC))
    with pytest.raises(ProgrammingError, match="permission denied"):
        await db_session.execute(
            text("UPDATE ads.impressions SET pincode = 'x' WHERE id = :a"), {"a": row_id}
        )
    await db_session.rollback()
    with pytest.raises(ProgrammingError, match="permission denied"):
        await db_session.execute(text("DELETE FROM ads.impressions WHERE id = :a"), {"a": row_id})
    await db_session.rollback()


async def test_append_only_trigger_cascades_to_partitions(db_session: AsyncSession) -> None:
    """Trigger-level immutability (holds against the OWNER too, not just
    app_rt): the BEFORE UPDATE OR DELETE trigger exists on the parent and is
    cloned onto every partition (PG16 row-trigger propagation), including the
    DEFAULT partition that catches unplanned days."""
    today = datetime.now(UTC).date()
    for table in (
        "impressions",
        "clicks",
        f"impressions_p{today:%Y%m%d}",
        "impressions_default",
        f"clicks_p{today:%Y%m%d}",
        "clicks_default",
    ):
        count = await db_session.scalar(
            text(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgrelid = CAST(:t AS regclass) AND tgname LIKE '%append_only%' "
                "AND NOT tgisinternal"
            ),
            {"t": f"ads.{table}"},
        )
        assert count == 1, f"missing append-only trigger on ads.{table}"


async def test_campaign_budget_columns_exist(db_session: AsyncSession) -> None:
    """M3: serve-credit budget columns (NULL total = unlimited)."""
    cols = set(
        (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'ads' AND table_name = 'campaigns'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert {"budget_serves_total", "budget_serves_used"} <= cols


async def test_campaign_budget_check_constraints(db_session: AsyncSession) -> None:
    with pytest.raises(Exception, match="ck_ads_campaigns_budget_total"):
        await db_session.execute(
            text(
                "INSERT INTO ads.campaigns "
                "(id, advertiser_business_id, name, status, budget_display, "
                " flight_start, flight_end, budget_serves_total) "
                "VALUES (gen_random_uuid(), gen_random_uuid(), 'bad-budget', 'draft', '', "
                "'2026-08-01', '2026-08-10', -1)"
            )
        )
    await db_session.rollback()


async def _insert_delivery_decision(session: AsyncSession) -> uuid.UUID:
    row_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO ads.delivery_decisions "
            "(id, campaign_id, placement_id, creative_id, slot_key, pincode, category, "
            " why_served, viewer_hash, occurred_at) "
            "VALUES (:id, gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), "
            "'milk_sponsored_listing', '641001', NULL, 'local_pincode', 'vh-test', now())"
        ),
        {"id": row_id},
    )
    return row_id


async def test_delivery_decisions_append_only_for_app_rt(db_session: AsyncSession) -> None:
    """M3.E: the why-served log is append-only BY GRANT for app_rt."""
    row_id = await _insert_delivery_decision(db_session)
    with pytest.raises(ProgrammingError, match="permission denied"):
        await db_session.execute(
            text("UPDATE ads.delivery_decisions SET slot_key = 'x' WHERE id = :a"),
            {"a": row_id},
        )
    await db_session.rollback()
    with pytest.raises(ProgrammingError, match="permission denied"):
        await db_session.execute(
            text("DELETE FROM ads.delivery_decisions WHERE id = :a"), {"a": row_id}
        )
    await db_session.rollback()


async def test_delivery_decisions_append_only_trigger(db_session: AsyncSession) -> None:
    """Trigger-level immutability holds against the owner role too (reuses
    0022's ads.forbid_tracking_mutation)."""
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM pg_trigger "
            "WHERE tgrelid = CAST('ads.delivery_decisions' AS regclass) "
            "AND tgname LIKE '%append_only%' AND NOT tgisinternal"
        )
    )
    assert count == 1


async def test_campaigns_flight_check_constraint(db_session: AsyncSession) -> None:
    with pytest.raises(Exception, match="ck_ads_campaigns_flight"):
        await db_session.execute(
            text(
                "INSERT INTO ads.campaigns "
                "(id, advertiser_business_id, name, status, budget_display, "
                " flight_start, flight_end) "
                "VALUES (gen_random_uuid(), gen_random_uuid(), 'bad', 'draft', '', "
                "'2026-08-10', '2026-08-01')"
            )
        )
    await db_session.rollback()
