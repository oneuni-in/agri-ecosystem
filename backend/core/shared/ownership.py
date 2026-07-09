"""Ownership scoping for user-owned rows.

Every service-layer query that returns user-owned data must pass through
owned_by() - see docs/backend-conventions.md.
"""

import uuid

from sqlalchemy import Select


def owned_by[T](
    query: Select[tuple[T]], user_id: uuid.UUID, *, column: str = "owner_id"
) -> Select[tuple[T]]:
    """Restrict a single-entity query to rows owned by user_id.

    Fails closed: a model without the ownership column raises TypeError
    instead of silently returning everyone's rows.
    """
    entity = query.column_descriptions[0]["entity"]
    ownership = getattr(entity, column, None)
    if entity is None or ownership is None:
        raise TypeError(f"{entity!r} has no ownership column {column!r} (default: owner_id)")
    return query.where(ownership == user_id)
