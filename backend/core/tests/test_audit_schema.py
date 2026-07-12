# backend/core/tests/test_audit_schema.py
"""D12 audit schema: table shape and app_rt grant matrix (non-negotiable:
the runtime role physically cannot UPDATE/DELETE audit rows)."""

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from settings import get_settings


async def test_audit_entries_table_exists_with_chain_columns(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'audit' AND table_name = 'entries'"
        )
    )
    columns = {row[0] for row in rows}
    assert {
        "id",
        "created_at",
        "actor_user_id",
        "action",
        "target_type",
        "target_id",
        "metadata",
        "ip",
        "chain_day",
        "seq",
        "prev_hash",
        "entry_hash",
    } <= columns
    assert "updated_at" not in columns  # append-only rows must not pretend to update


async def test_app_rt_role_has_no_update_or_delete_on_audit(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'app_rt' AND table_schema = 'audit' AND table_name = 'entries'"
        )
    )
    privileges = {row[0] for row in rows}
    assert privileges == {"INSERT", "SELECT"}


def test_runtime_url_is_app_rt_and_admin_url_is_app() -> None:
    assert make_url(get_settings().database_url).username == "app_rt"
    assert make_url(get_settings().database_admin_url).username == "app"
