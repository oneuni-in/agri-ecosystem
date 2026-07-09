"""Base mixins: a model composed only of mixins gets UUIDv7 PK, UTC audit
timestamps, default-filtered soft-delete, and pending-by-default moderation
with zero extra code (D03 non-negotiable 2)."""

import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UGCMixin,
    UUIDv7PKMixin,
    soft_delete,
)


class MixinWidget(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, UGCMixin, Base):
    __tablename__ = "test_mixin_widgets"
    __table_args__ = {"schema": "content"}

    name: Mapped[str] = mapped_column()


async def _create_table(session: AsyncSession) -> None:
    conn = await session.connection()
    table = Base.metadata.tables["content.test_mixin_widgets"]
    await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[table]))


async def test_mixin_model_gets_uuid7_pk(db_session: AsyncSession) -> None:
    await _create_table(db_session)
    widget = MixinWidget(name="first")
    db_session.add(widget)
    await db_session.flush()

    assert isinstance(widget.id, uuid.UUID)
    assert widget.id.version == 7


async def test_uuid7_pks_are_time_ordered(db_session: AsyncSession) -> None:
    await _create_table(db_session)
    first = MixinWidget(name="first")
    second = MixinWidget(name="second")
    db_session.add_all([first, second])
    await db_session.flush()

    assert first.id < second.id


async def test_timestamps_are_utc_server_defaults(db_session: AsyncSession) -> None:
    await _create_table(db_session)
    widget = MixinWidget(name="stamped")
    db_session.add(widget)
    await db_session.flush()
    await db_session.refresh(widget)

    assert widget.created_at.tzinfo is not None
    assert widget.created_at.astimezone(UTC) == widget.created_at
    assert widget.updated_at >= widget.created_at


async def test_updated_at_bumps_on_update(db_session: AsyncSession) -> None:
    await _create_table(db_session)
    widget = MixinWidget(name="before")
    db_session.add(widget)
    await db_session.flush()
    await db_session.refresh(widget)
    original = widget.updated_at

    widget.name = "after"
    await db_session.flush()
    await db_session.refresh(widget)

    assert widget.updated_at > original


async def test_soft_deleted_rows_hidden_by_default(db_session: AsyncSession) -> None:
    await _create_table(db_session)
    live = MixinWidget(name="live")
    dead = MixinWidget(name="dead")
    db_session.add_all([live, dead])
    await db_session.flush()

    soft_delete(dead)
    await db_session.flush()
    db_session.expunge_all()

    names = (await db_session.scalars(select(MixinWidget.name))).all()
    assert names == ["live"]


async def test_soft_deleted_rows_visible_with_include_deleted(db_session: AsyncSession) -> None:
    await _create_table(db_session)
    live = MixinWidget(name="live")
    dead = MixinWidget(name="dead")
    db_session.add_all([live, dead])
    await db_session.flush()
    soft_delete(dead)
    await db_session.flush()
    db_session.expunge_all()

    rows = (
        await db_session.scalars(select(MixinWidget).execution_options(include_deleted=True))
    ).all()
    assert sorted(row.name for row in rows) == ["dead", "live"]
    assert next(r for r in rows if r.name == "dead").deleted_at is not None


async def test_ugc_defaults_to_pending(db_session: AsyncSession) -> None:
    await _create_table(db_session)
    widget = MixinWidget(name="ugc")
    db_session.add(widget)
    await db_session.flush()
    await db_session.refresh(widget)

    assert widget.moderation_status == "pending"
