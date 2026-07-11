"""Identity ORM models stay in lockstep with migrations 0007/0009, and the D03
mixins (UUIDv7 PK, soft-delete default filter, unique phone) behave on the
real tables."""

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import modules.identity.models  # noqa: F401 - registers tables on Base.metadata
from shared.db import Base, soft_delete

IDENTITY_TABLES = (
    "users",
    "handles_history",
    "otp_requests",
    "sessions_refresh",
    "emails",
    "roles",
    "permissions",
    "role_permissions",
    "user_roles",
    "profiles",
    "addresses",
    "preferences",
    "oauth_clients",
    "oauth_codes",
)


async def test_orm_and_migration_agree_on_every_column(db_session: AsyncSession) -> None:
    conn = await db_session.connection()

    def _db_columns(sync_conn: Connection) -> dict[str, set[str]]:
        inspector = sa_inspect(sync_conn)
        return {
            table: {col["name"] for col in inspector.get_columns(table, schema="identity")}
            for table in IDENTITY_TABLES
        }

    db_columns = await conn.run_sync(_db_columns)
    for table in IDENTITY_TABLES:
        orm_table = Base.metadata.tables[f"identity.{table}"]
        orm_columns = {column.name for column in orm_table.columns}
        assert orm_columns == db_columns[table], f"identity.{table} drifted from migration 0007"


async def test_user_gets_uuid7_pk_and_defaults(db_session: AsyncSession) -> None:
    from modules.identity.models import User

    user = User(phone="+919876543210", agri_id="AG-0000001")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.id.version == 7
    assert user.status == "active"
    assert user.agri_id_changed_once is False
    assert user.phone_verified_at is None
    assert user.created_at.tzinfo is not None


async def test_one_account_per_phone(db_session: AsyncSession) -> None:
    from modules.identity.models import User

    db_session.add(User(phone="+919876543210", agri_id="AG-0000001"))
    await db_session.flush()
    db_session.add(User(phone="+919876543210", agri_id="AG-0000002"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_soft_deleted_users_hidden_by_default(db_session: AsyncSession) -> None:
    from modules.identity.models import User

    live = User(phone="+919876543210", agri_id="AG-0000001")
    dead = User(phone="+919876543211", agri_id="AG-0000002")
    db_session.add_all([live, dead])
    await db_session.flush()
    soft_delete(dead)
    await db_session.flush()
    db_session.expunge_all()

    phones = (await db_session.scalars(select(User.phone))).all()
    assert phones == ["+919876543210"]


async def test_profile_defaults(db_session: AsyncSession) -> None:
    from modules.identity.models import Profile, User

    user = User(phone="+919876543210", agri_id="AG-0000001")
    db_session.add(user)
    await db_session.flush()
    profile = Profile(user_id=user.id)
    db_session.add(profile)
    await db_session.flush()
    await db_session.refresh(profile)

    assert profile.language == "en"
    assert profile.interests == []
    assert profile.completion_score == 0
