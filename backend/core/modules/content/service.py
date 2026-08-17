"""Content module public service interface (E6, A-U3).

The read path has exactly one gate: `moderation_status == 'approved'`.
Everything public flows through `_published()`, so there is no query in
this module that could return a pending item to a reader — the gate is
structural, not a condition each caller remembers to add.

Ordering deserves a note. Items are keyset-paginated on the UUIDv7 id
(the only sanctioned mechanism, ADR-0004), which orders by INGEST time,
while cards display the PUBLISHER's `published_at`. For a feed that is
the right trade: back-dated items would otherwise be buried where nobody
would ever page to them, and each card carries its own date so the order
is never misread.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import uuid6
from sqlalchemy import CursorResult, Select, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.pagination import Page, paginate

from .models import KINDS, Bookmark, ContentItem

APPROVED = "approved"
PENDING = "pending"
REJECTED = "rejected"

# A reader cannot save an unbounded number of items to a table we then
# have to join on. Generous enough that no real reader meets it.
BOOKMARK_CAP = 500


class BookmarkCapReached(Exception):
    """The caller already holds BOOKMARK_CAP bookmarks."""


class UnknownKind(ValueError):
    """A kind outside the module's vocabulary."""


def _published() -> Select[tuple[ContentItem]]:
    """THE public read. Every reader-facing query starts here."""
    return select(ContentItem).where(ContentItem.moderation_status == APPROVED)


def _tagged(
    query: Select[tuple[ContentItem]], *, vertical: str | None, state: str | None
) -> Select[tuple[ContentItem]]:
    """Narrow by vertical/state tags.

    JSONB containment (`@>`) rather than a Python filter, so paging stays
    correct: filtering after the LIMIT would return short pages and a
    cursor that skips rows.
    """
    if vertical:
        query = query.where(ContentItem.verticals.contains([vertical]))
    if state:
        query = query.where(ContentItem.states.contains([state]))
    return query


async def list_feed(
    session: AsyncSession,
    *,
    kind: str | None = None,
    vertical: str | None = None,
    state: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> Page[ContentItem]:
    """Approved items, newest-ingested first."""
    if kind is not None and kind not in KINDS:
        raise UnknownKind(kind)
    query = _tagged(_published(), vertical=vertical, state=state)
    if kind is not None:
        query = query.where(ContentItem.kind == kind)
    return await paginate(session, query, cursor=cursor, limit=limit, descending=True)


async def get_item(session: AsyncSession, slug: str) -> ContentItem | None:
    """One approved item by its immutable slug. `None` for a pending,
    rejected or nonexistent slug — the same answer for all three, so the
    read cannot be used to discover what is sitting in the queue."""
    return cast(
        "ContentItem | None", await session.scalar(_published().where(ContentItem.slug == slug))
    )


async def count_published(session: AsyncSession, *, kind: str | None = None) -> int:
    """How many approved items exist.

    The honesty rule needs this: the home's knowledge row is ABSENT when
    the module is empty, and "absent" has to be decided from a count, not
    from an empty list arriving after the section header was rendered.
    """
    query = select(ContentItem.id).where(ContentItem.moderation_status == APPROVED)
    if kind is not None:
        query = query.where(ContentItem.kind == kind)
    return len((await session.scalars(query)).all())


# ── moderation (the human gate) ──────────────────────────────────────


async def list_queue(
    session: AsyncSession,
    *,
    status: str = PENDING,
    cursor: str | None = None,
    limit: int = 20,
) -> Page[ContentItem]:
    """The moderation queue. Behind `content.read` at the route."""
    query = select(ContentItem).where(ContentItem.moderation_status == status)
    return await paginate(session, query, cursor=cursor, limit=limit, descending=True)


async def set_moderation(
    session: AsyncSession, item_id: uuid.UUID, *, status: str
) -> ContentItem | None:
    """Move one item through the gate. Callers must already hold
    `content.publish`; this function does not re-check, it records.

    Idempotent: approving an approved item is a no-op rather than an
    error, so a double-click in the CMS cannot fail.
    """
    if status not in (APPROVED, PENDING, REJECTED):
        raise ValueError(f"unknown moderation status: {status!r}")
    item = await session.scalar(select(ContentItem).where(ContentItem.id == item_id))
    if item is None:
        return None
    item.moderation_status = status
    await session.flush()
    return item


async def create_item(session: AsyncSession, **fields: Any) -> ContentItem:
    """Create a first-party item.

    `moderation_status` is stripped rather than honoured: the CMS must
    not be able to create something already approved, or the gate becomes
    a suggestion. New rows take UGCMixin's `pending` default and go
    through `set_moderation` like everything else.
    """
    fields.pop("moderation_status", None)
    item = ContentItem(**fields)
    session.add(item)
    await session.flush()
    return item


# ── bookmarks ────────────────────────────────────────────────────────


async def list_bookmarks(
    session: AsyncSession, user_id: uuid.UUID, *, cursor: str | None = None, limit: int = 20
) -> Page[ContentItem]:
    """The caller's saved items — approved ones only.

    An item unapproved after it was saved drops out of the list rather
    than reappearing on a reader's shelf; the bookmark row survives, so
    it comes back if the item is approved again.
    """
    query = (
        _published()
        .join(Bookmark, Bookmark.item_id == ContentItem.id)
        .where(Bookmark.user_id == user_id)
    )
    return await paginate(session, query, cursor=cursor, limit=limit, descending=True)


async def add_bookmark(session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> bool:
    """Save an item. Returns False when the item is not readable by this
    caller — an unapproved or nonexistent id is the same answer, so the
    endpoint cannot enumerate the moderation queue.

    ON CONFLICT DO NOTHING: the UI's control is a toggle with no
    "already saved" state, so saving twice must be harmless.
    """
    if await session.scalar(_published().where(ContentItem.id == item_id)) is None:
        return False

    rows = await session.scalars(select(Bookmark.id).where(Bookmark.user_id == user_id))
    held = len(rows.all())
    if held >= BOOKMARK_CAP:
        raise BookmarkCapReached

    try:
        await session.execute(
            pg_insert(Bookmark)
            # uuid7, not uuid4 (ADR-0003): the core insert bypasses the
            # ORM default, and a uuid4 here would break keyset paging,
            # which orders bookmarks by their time-sortable id.
            .values(id=uuid6.uuid7(), user_id=user_id, item_id=item_id)
            .on_conflict_do_nothing(index_elements=["user_id", "item_id"])
        )
    except IntegrityError:  # pragma: no cover - covered by DO NOTHING
        return True
    await session.flush()
    return True


async def remove_bookmark(session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> bool:
    """Unsave. False when this caller holds no such bookmark — another
    user's bookmark and a nonexistent one are indistinguishable (the U2
    IDOR rule)."""
    # cast for the same reason ads/service.py does: session.execute()'s
    # overloads resolve a DML statement to Result[Any], which has no
    # rowcount, though CursorResult is what actually comes back.
    result = cast(
        CursorResult[Any],
        await session.execute(
            delete(Bookmark).where(Bookmark.user_id == user_id, Bookmark.item_id == item_id)
        ),
    )
    await session.flush()
    return bool(result.rowcount)


async def bookmarked_ids(
    session: AsyncSession, user_id: uuid.UUID, item_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of `item_ids` this caller has saved — one query for a whole
    page of cards, so the feed does not fire N reads to fill N toggles."""
    if not item_ids:
        return set()
    rows = await session.scalars(
        select(Bookmark.item_id).where(Bookmark.user_id == user_id, Bookmark.item_id.in_(item_ids))
    )
    return set(rows.all())
