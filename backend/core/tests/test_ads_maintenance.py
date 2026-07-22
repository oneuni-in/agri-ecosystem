"""Partition maintenance: idempotent daily pre-create via the ADMIN engine
(partition DDL is owner work - app_rt has no CREATE, by design)."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine

from modules.ads import maintenance, worker
from settings import get_settings

pytestmark = pytest.mark.asyncio


def _admin_url(runtime_url: str) -> str:
    """The test DB with the admin role's credentials (conftest gives app_rt).

    Uses render_as_string(hide_password=False) - plain str(URL) masks the
    password as "***" (SQLAlchemy 2.0 default), which asyncpg would then try
    to authenticate with literally (see tests/conftest.py precedent)."""
    admin = make_url(get_settings().database_admin_url)
    return (
        make_url(runtime_url)
        .set(username=admin.username, password=admin.password)
        .render_as_string(hide_password=False)
    )


@pytest.fixture
async def admin_conn(database_url: str) -> AsyncIterator[AsyncConnection]:
    """AUTOCOMMIT: ensure_partitions' CREATE TABLE must be visible to
    db_session's separate connection within the same test (engine.begin()
    would hold the DDL uncommitted until fixture teardown, after the test
    body's assertions already ran - conftest.py's database_url fixture uses
    the same AUTOCOMMIT pattern for DDL against a second connection)."""
    engine = create_async_engine(_admin_url(database_url), isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


def test_partition_name() -> None:
    assert maintenance.partition_name("impressions", date(2026, 7, 21)) == ("impressions_p20260721")


async def test_ensure_partitions_creates_ahead_and_is_idempotent(
    admin_conn: AsyncConnection, db_session: AsyncSession
) -> None:
    start = datetime.now(UTC).date() + timedelta(days=20)  # beyond migration's +7
    created = await maintenance.ensure_partitions(admin_conn, start=start, days_ahead=2)
    # 2 tables x 3 days (start .. start+2)
    assert len(created) == 6
    again = await maintenance.ensure_partitions(admin_conn, start=start, days_ahead=2)
    assert again == []  # idempotent: IF NOT EXISTS, nothing re-created
    exists = await db_session.scalar(
        text("SELECT to_regclass(:n) IS NOT NULL"),
        {"n": f"ads.{maintenance.partition_name('clicks', start + timedelta(days=2))}"},
    )
    assert exists is True


async def test_new_partition_inherits_append_only_trigger(
    admin_conn: AsyncConnection, db_session: AsyncSession
) -> None:
    start = datetime.now(UTC).date() + timedelta(days=25)
    await maintenance.ensure_partitions(admin_conn, start=start, days_ahead=0)
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM pg_trigger "
            "WHERE tgrelid = CAST(:t AS regclass) AND tgname LIKE '%append_only%' "
            "AND NOT tgisinternal"
        ),
        {"t": f"ads.{maintenance.partition_name('impressions', start)}"},
    )
    assert count == 1


async def test_worker_tick_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """ads_worker_enabled=false -> zero work, zero DB connections."""
    monkeypatch.setenv("ADS_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert await worker.worker_tick() == 0
    finally:
        get_settings.cache_clear()
