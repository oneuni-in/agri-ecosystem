"""Keyset pagination over UUIDv7 primary keys.

paginate() is the only sanctioned list mechanism (offset pagination collapses
at scale and is banned by a lint contract). Cursors are opaque url-safe
strings encoding the last-seen id; UUIDv7 ordering makes id-keyset paging
time-ordered for free.
"""

import base64
import uuid
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class InvalidCursorError(ValueError):
    """The supplied cursor is not one we issued."""


@runtime_checkable
class HasId(Protocol):
    """Anything with a UUID primary key (every UUIDv7PKMixin model).

    runtime_checkable because Page[T]'s eager parametrization builds an
    isinstance validator from the bound."""

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
    descending: bool = False,
) -> Page[T]:
    """Return one keyset page of an id-ordered model query.

    The query must select a single ORM entity with an ``id`` primary key
    (every table built on UUIDv7PKMixin qualifies). Ordering is applied here;
    callers must not order the query themselves. descending=True pages
    newest-first (notifications).
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
        last_seen = decode_cursor(cursor)
        stmt = stmt.where(id_column < last_seen if descending else id_column > last_seen)
    order_col = id_column.desc() if descending else id_column
    stmt = stmt.order_by(order_col).limit(limit + 1)

    rows = (await session.scalars(stmt)).all()
    items = list(rows[:limit])
    next_cursor = encode_cursor(items[-1].id) if len(rows) > limit else None
    return Page(items=items, next_cursor=next_cursor)
