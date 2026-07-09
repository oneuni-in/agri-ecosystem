"""Keyset pagination over UUIDv7 primary keys.

paginate() is the only sanctioned list mechanism (offset pagination collapses
at scale and is banned by a lint contract). Cursors are opaque url-safe
strings encoding the last-seen id; UUIDv7 ordering makes id-keyset paging
time-ordered for free.
"""

import base64
import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class InvalidCursorError(ValueError):
    """The supplied cursor is not one we issued."""


class HasId(Protocol):
    id: uuid.UUID


class Page[T](BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    next_cursor: str | None = None


def encode_cursor(last_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(last_id.bytes).decode().rstrip("=")


def decode_cursor(cursor: str) -> uuid.UUID:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        return uuid.UUID(bytes=base64.urlsafe_b64decode(padded))
    except (ValueError, TypeError) as exc:
        raise InvalidCursorError(f"malformed cursor: {cursor!r}") from exc


async def paginate[T: HasId](
    session: AsyncSession,
    query: Select[tuple[T]],
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[T]:
    """Return one keyset page of an id-ordered model query.

    The query must select a single ORM entity with an ``id`` primary key
    (every table built on UUIDv7PKMixin qualifies). Ordering is applied here;
    callers must not order the query themselves.
    """
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    limit = min(limit, MAX_PAGE_SIZE)

    entity = query.column_descriptions[0]["entity"]
    id_column = getattr(entity, "id", None)
    if entity is None or id_column is None:
        raise TypeError("paginate() requires a single-entity query with an id primary key")

    stmt = query
    if cursor is not None:
        stmt = stmt.where(id_column > decode_cursor(cursor))
    stmt = stmt.order_by(id_column).limit(limit + 1)

    rows = (await session.scalars(stmt)).all()
    items = list(rows[:limit])
    next_cursor = encode_cursor(items[-1].id) if len(rows) > limit else None
    return Page(items=items, next_cursor=next_cursor)
