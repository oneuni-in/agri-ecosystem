"""covers(pincode): distance-ordered, keyset-paginated vendor discovery (D15.B).

Distance anchor: nearest geocoded branch; fallback to the centroid of the
business's primary_pincode; UNLOCATABLE_M sentinel when neither resolves so
every covering business still appears (last). Distances are integer metres so
the (distance_m, id) keyset comparison is exact.

Keyset, not offset: the cursor encodes (distance_m, last_id) and the page
predicate is a strict lexicographic step - deep-offset enumeration is
structurally impossible (THREAT: covers() scraping; rate limit is the other
half of that defence).

Raw SQL bypasses the ORM soft-delete filter, so deleted_at IS NULL is
enforced explicitly on both businesses and branches.
"""

import base64
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, InvalidCursorError

# Farther than any point on Earth (~2e7 m): unlocatable businesses sort last.
UNLOCATABLE_M = 1_000_000_000


@dataclass(frozen=True, slots=True)
class CoversItem:
    id: uuid.UUID
    name: str
    slug: str
    type: str
    verification_status: str
    subscription_tier: str
    primary_pincode: str
    distance_m: int


@dataclass(frozen=True, slots=True)
class CoversPage:
    items: list[CoversItem]
    next_cursor: str | None


def encode_covers_cursor(distance_m: int, last_id: uuid.UUID) -> str:
    raw = f"{distance_m}:{last_id.hex}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_covers_cursor(cursor: str) -> tuple[int, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        distance, _, id_hex = base64.urlsafe_b64decode(padded).decode().partition(":")
        return int(distance), uuid.UUID(hex=id_hex)
    except (ValueError, TypeError) as exc:
        raise InvalidCursorError(f"malformed cursor: {cursor!r}") from exc


def _haversine_m(lat1: str, lon1: str, lat2: str, lon2: str) -> str:
    """SQL text: great-circle metres between two lat/lon SQL expressions."""
    return (
        f"2 * 6371000.0 * asin(sqrt("
        f"power(sin(radians(({lat2}) - ({lat1})) / 2), 2) + "
        f"cos(radians({lat1})) * cos(radians({lat2})) * "
        f"power(sin(radians(({lon2}) - ({lon1})) / 2), 2)))"
    )


_BRANCH_DISTANCE = _haversine_m("q.lat", "q.lon", "br.lat", "br.lng")
_PRIMARY_DISTANCE = _haversine_m("q.lat", "q.lon", "p.centroid_lat", "p.centroid_lon")

_BASE_SQL = f"""
WITH q AS (
    SELECT centroid_lat AS lat, centroid_lon AS lon
    FROM geo.pincodes WHERE pincode = :pincode
)
SELECT b.id, b.name, b.slug, b.type, b.verification_status,
       b.subscription_tier, b.primary_pincode, d.distance_m
FROM directory.businesses b
JOIN directory.business_coverage c
  ON c.business_id = b.id AND c.pincode = :pincode
CROSS JOIN q
CROSS JOIN LATERAL (
    SELECT CAST(ROUND(COALESCE(
        (SELECT MIN({_BRANCH_DISTANCE}) FROM directory.branches br
         WHERE br.business_id = b.id
           AND br.lat IS NOT NULL AND br.lng IS NOT NULL
           AND br.deleted_at IS NULL),
        (SELECT {_PRIMARY_DISTANCE} FROM geo.pincodes p
         WHERE p.pincode = b.primary_pincode),
        {UNLOCATABLE_M}
    )) AS BIGINT) AS distance_m
) d
WHERE b.status = 'active' AND b.deleted_at IS NULL
"""

_CURSOR_PREDICATE = """
  AND (d.distance_m > :cursor_distance
       OR (d.distance_m = :cursor_distance AND b.id > :cursor_id))
"""

_ORDER_LIMIT = "\nORDER BY d.distance_m, b.id\nLIMIT :lim"

_CATEGORY_PREDICATE = """
  AND EXISTS (
      SELECT 1 FROM directory.business_categories bc
      JOIN directory.categories cat ON cat.id = bc.category_id
      WHERE bc.business_id = b.id AND cat.slug = :category
  )
"""


async def covers(
    session: AsyncSession,
    *,
    pincode: str,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    category: str | None = None,
) -> CoversPage:
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    limit = min(limit, MAX_PAGE_SIZE)
    sql = _BASE_SQL
    params: dict[str, object] = {"pincode": pincode, "lim": limit + 1}
    if category is not None:
        sql += _CATEGORY_PREDICATE
        params["category"] = category
    if cursor is not None:
        cursor_distance, cursor_id = decode_covers_cursor(cursor)
        sql += _CURSOR_PREDICATE
        params |= {"cursor_distance": cursor_distance, "cursor_id": cursor_id}
    rows = (await session.execute(text(sql + _ORDER_LIMIT), params)).all()
    items = [
        CoversItem(
            id=m["id"],
            name=m["name"],
            slug=m["slug"],
            type=m["type"],
            verification_status=m["verification_status"],
            subscription_tier=m["subscription_tier"],
            primary_pincode=m["primary_pincode"],
            distance_m=int(m["distance_m"]),
        )
        for m in (row._mapping for row in rows[:limit])
    ]
    next_cursor = (
        encode_covers_cursor(items[-1].distance_m, items[-1].id) if len(rows) > limit else None
    )
    return CoversPage(items=items, next_cursor=next_cursor)
