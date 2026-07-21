"""The unified moderation queue registry (D21) - the sprint's shared-surface
contract: a future module (forum, classifieds) plugs in by registering a
source; nothing imports across modules."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from shared.moderation import (
    ModDecision,
    ModItem,
    PendingEvent,
    get_source,
    iter_sources,
    register_moderation_source,
    reset_moderation_sources,
)
from shared.pagination import Page


def _item(type_key: str) -> ModItem:
    return ModItem(
        type_key=type_key,
        id=uuid.uuid4(),
        created_at=datetime.now(UTC),
        title="t",
        summary="s",
        payload={},
    )


class FakeSource:
    type_key = "fake"

    async def count_pending(self, session: AsyncSession) -> int:
        return 1

    async def list_pending(
        self, session: AsyncSession, *, cursor: str | None, limit: int
    ) -> Page[ModItem]:
        return Page(items=[_item("fake")], next_cursor=None)

    async def approve(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
    ) -> ModDecision:
        return ModDecision(item=_item("fake"), events=(PendingEvent("s", "t", {}),))

    async def reject(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
    ) -> ModDecision:
        return ModDecision(item=_item("fake"), events=())


def test_register_get_iter_reset() -> None:
    reset_moderation_sources()
    assert get_source("fake") is None
    src = FakeSource()
    register_moderation_source(src)
    assert get_source("fake") is src
    register_moderation_source(FakeSource())  # re-register same key: replaces, no error
    assert get_source("fake") is not src
    assert [s.type_key for s in iter_sources()] == ["fake"]
    reset_moderation_sources()
    assert iter_sources() == ()


def test_sources_iterate_sorted() -> None:
    reset_moderation_sources()

    class B(FakeSource):
        type_key = "bbb"

    class A(FakeSource):
        type_key = "aaa"

    register_moderation_source(B())
    register_moderation_source(A())
    assert [s.type_key for s in iter_sources()] == ["aaa", "bbb"]
    reset_moderation_sources()
