"""The demo migration (0005) must produce exactly the one-way-door column set,
proving hand-written migrations built from shared/migrations.py stay in
lockstep with the ORM mixins."""

from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import ReflectedColumn
from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_COLUMNS = {
    "id",
    "created_at",
    "updated_at",
    "deleted_at",
    "moderation_status",
    "slug",
    "title",
}


async def test_demo_table_has_every_mixin_column(db_session: AsyncSession) -> None:
    conn = await db_session.connection()

    def _columns(sync_conn: Connection) -> dict[str, ReflectedColumn]:
        return {c["name"]: c for c in inspect(sync_conn).get_columns("_demo_all_mixins")}

    columns = await conn.run_sync(_columns)

    assert set(columns) == EXPECTED_COLUMNS
    assert columns["id"]["nullable"] is False
    assert columns["deleted_at"]["nullable"] is True
    assert getattr(columns["created_at"]["type"], "timezone", False) is True
    assert getattr(columns["updated_at"]["type"], "timezone", False) is True
    assert columns["moderation_status"]["default"] == "'pending'::moderation_status"
