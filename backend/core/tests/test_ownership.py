"""owned_by(): the one way to scope a query to its owner - fails closed when
the model has no ownership column."""

import uuid

import pytest
import uuid6
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UUIDv7PKMixin
from shared.ownership import owned_by


class OwnedThing(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "test_owned_things"
    __table_args__ = {"schema": "content"}

    owner_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True))
    name: Mapped[str] = mapped_column()


class UnownedThing(UUIDv7PKMixin, Base):
    __tablename__ = "test_unowned_things"
    __table_args__ = {"schema": "content"}


async def test_owned_by_filters_to_the_given_user(db_session: AsyncSession) -> None:
    conn = await db_session.connection()
    table = Base.metadata.tables["content.test_owned_things"]
    await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[table]))

    alice, bob = uuid6.uuid7(), uuid6.uuid7()
    db_session.add_all(
        [
            OwnedThing(owner_id=alice, name="alice-1"),
            OwnedThing(owner_id=bob, name="bob-1"),
            OwnedThing(owner_id=alice, name="alice-2"),
        ]
    )
    await db_session.flush()

    rows = (await db_session.scalars(owned_by(select(OwnedThing), alice))).all()
    assert sorted(row.name for row in rows) == ["alice-1", "alice-2"]


def test_owned_by_fails_closed_without_ownership_column() -> None:
    with pytest.raises(TypeError, match="owner_id"):
        owned_by(select(UnownedThing), uuid6.uuid7())


def test_owned_by_supports_custom_column_name() -> None:
    query = owned_by(select(OwnedThing), uuid6.uuid7(), column="owner_id")
    assert "owner_id" in str(query)
