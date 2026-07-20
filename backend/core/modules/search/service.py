"""Unified public search (D19 Task 5): fan the app's one `GET /search` call
into a single per-site Meilisearch query, applying filters, an optional
pincode geo-boost, and a bespoke opaque cursor.

Bespoke cursor, not shared.pagination: Meili result sets are relevance-
ordered, not UUID-keyset-able, so the precedent here is
modules/directory/covers.py's bespoke (distance, id) cursor, not
shared/pagination.py's id-keyset paginate(). The cursor encodes the Meili
`offset` to resume from plus a hash of the query params it was issued for
(`qhash`), so a cursor minted for one query can never be replayed against a
different one - decode_search_cursor rejects both a tampered payload and a
mismatched qhash the same way (InvalidSearchCursor -> 400 at the router).
"""

import base64
import binascii
import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.geo.service import centroid_for_pincode

from .client import get_meili
from .indexing import index_uid

MAX_DEPTH = 500  # bounded exploration; deep scraping goes through covers()/lists instead


class InvalidSearchCursor(ValueError):
    pass


def _query_hash(
    site: str,
    q: str,
    pincode: str | None,
    kind: str | None,
    vertical: str | None,
    covered: bool,
    limit: int,
) -> str:
    raw = "|".join([site, q, pincode or "", kind or "", vertical or "", str(covered), str(limit)])
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def encode_search_cursor(start: int, qhash: str) -> str:
    return base64.urlsafe_b64encode(json.dumps({"s": start, "h": qhash}).encode()).decode()


def decode_search_cursor(cursor: str, qhash: str) -> int:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        # A cursor is base64 JSON we minted; anything that decodes to valid
        # JSON but isn't the {"s", "h"} object we wrote (e.g. base64 of a
        # bare `123` or `null`) must still be a 400, not a TypeError on
        # `data["s"]` escaping as an unhandled 500.
        if not isinstance(data, dict):
            raise InvalidSearchCursor(cursor)
        start = int(data["s"])
        # >= not >: encode_search_cursor only ever mints next_start < MAX_DEPTH
        # (see run_search), so a legitimately-issued cursor's start is always
        # in [0, MAX_DEPTH); start == MAX_DEPTH is already outside anything we
        # would issue and must be rejected at the boundary, not one past it.
        if data["h"] != qhash or start < 0 or start >= MAX_DEPTH:
            raise InvalidSearchCursor(cursor)
        return start
    except (ValueError, KeyError, binascii.Error) as exc:
        raise InvalidSearchCursor(cursor) from exc


async def run_search(
    session: AsyncSession,
    *,
    site: str,
    q: str,
    pincode: str | None = None,
    kind: str | None = None,
    vertical: str | None = None,
    covered: bool = False,
    cursor: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    qhash = _query_hash(site, q, pincode, kind, vertical, covered, limit)
    start = decode_search_cursor(cursor, qhash) if cursor else 0
    filters: list[str] = []
    if kind:
        filters.append(f'kind = "{kind}"')
    if vertical:
        filters.append(f'vertical = "{vertical}"')
    if covered and pincode:
        filters.append(f'covered_pincodes = "{pincode}"')
    body: dict[str, Any] = {"q": q, "limit": limit + 1, "offset": start}
    if filters:
        body["filter"] = " AND ".join(filters)
    if pincode:
        centroid = await centroid_for_pincode(session, pincode)
        if centroid is not None:
            lat, lon = centroid
            body["sort"] = [f"_geoPoint({float(lat)}, {float(lon)}):asc"]
    result = await get_meili().search(index_uid(site), body)
    hits = result["hits"]
    has_more = len(hits) > limit
    items = hits[:limit]
    next_start = start + limit
    next_cursor = (
        encode_search_cursor(next_start, qhash) if has_more and next_start < MAX_DEPTH else None
    )
    return {"items": items, "next_cursor": next_cursor}
