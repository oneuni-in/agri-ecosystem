"""Deliberately-bad demo file: OFFSET pagination (banned, D03 lint contract)."""

from sqlalchemy import Select


def bad_page(query: Select[tuple[object]], page: int, size: int) -> Select[tuple[object]]:
    return query.limit(size).offset(page * size)
