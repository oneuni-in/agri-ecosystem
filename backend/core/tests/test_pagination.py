"""Keyset pagination: the only list mechanism (D03 non-negotiable 3)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, SoftDeleteMixin, TimestampMixin, UUIDv7PKMixin, soft_delete
from shared.pagination import InvalidCursorError, Page, paginate


class PageItem(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "test_page_items"
    __table_args__ = {"schema": "content"}

    name: Mapped[str] = mapped_column()


async def _seed(session: AsyncSession, count: int) -> list[PageItem]:
    conn = await session.connection()
    table = Base.metadata.tables["content.test_page_items"]
    await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[table]))
    items = [PageItem(name=f"item-{i:03d}") for i in range(count)]
    session.add_all(items)
    await session.flush()
    return items


async def test_first_page_is_id_ordered_with_cursor(db_session: AsyncSession) -> None:
    await _seed(db_session, 5)
    page = await paginate(db_session, select(PageItem), limit=3)

    assert isinstance(page, Page)
    assert [item.name for item in page.items] == ["item-000", "item-001", "item-002"]
    assert page.next_cursor is not None


async def test_cursor_walks_the_full_set_exactly_once(db_session: AsyncSession) -> None:
    await _seed(db_session, 7)
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        page = await paginate(db_session, select(PageItem), cursor=cursor, limit=3)
        seen.extend(item.name for item in page.items)
        pages += 1
        if page.next_cursor is None:
            break
        cursor = page.next_cursor

    assert seen == [f"item-{i:03d}" for i in range(7)]
    assert pages == 3


async def test_last_page_has_no_cursor_even_when_full(db_session: AsyncSession) -> None:
    await _seed(db_session, 3)
    page = await paginate(db_session, select(PageItem), limit=3)
    assert len(page.items) == 3
    assert page.next_cursor is None


async def test_invalid_cursor_raises(db_session: AsyncSession) -> None:
    await _seed(db_session, 1)
    with pytest.raises(InvalidCursorError):
        await paginate(db_session, select(PageItem), cursor="not-a-cursor")


async def test_limit_is_clamped(db_session: AsyncSession) -> None:
    await _seed(db_session, 2)
    page = await paginate(db_session, select(PageItem), limit=5000)
    assert len(page.items) == 2
    with pytest.raises(ValueError, match="limit"):
        await paginate(db_session, select(PageItem), limit=0)


async def test_paginate_respects_soft_delete_filter(db_session: AsyncSession) -> None:
    items = await _seed(db_session, 4)
    soft_delete(items[1])
    await db_session.flush()
    db_session.expunge_all()

    page = await paginate(db_session, select(PageItem), limit=10)
    assert [item.name for item in page.items] == ["item-000", "item-002", "item-003"]


async def test_paginate_descending_orders_newest_first(db_session: AsyncSession) -> None:
    await _seed(db_session, 5)
    page = await paginate(db_session, select(PageItem), limit=2, descending=True)
    ids = [item.id for item in page.items]
    assert ids == sorted(ids, reverse=True)
    assert page.next_cursor is not None
    page2 = await paginate(
        db_session, select(PageItem), cursor=page.next_cursor, limit=2, descending=True
    )
    assert all(item.id < min(ids) for item in page2.items)
