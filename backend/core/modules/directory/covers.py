"""covers(pincode): distance-ordered, keyset-paginated vendor discovery (D15.B).

Distance anchor: nearest geocoded branch; fallback to the centroid of the
business's primary_pincode; UNLOCATABLE_M sentinel when neither resolves so
every covering business still appears (last). Distances are integer metres so
the (distance_m, id) keyset comparison is exact.

Keyset, not offset: the cursor encodes (verified_rank, tier_rank, distance_m,
last_id) and the page predicate is a strict lexicographic step - deep-offset
enumeration is structurally impossible (THREAT: covers() scraping; rate limit
is the other half of that defence).

Raw SQL bypasses the ORM soft-delete filter, so deleted_at IS NULL is
enforced explicitly on both businesses and branches.
"""

import base64
import uuid
from dataclasses import dataclass
from decimal import Decimal

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
    lat: Decimal | None
    lng: Decimal | None


@dataclass(frozen=True, slots=True)
class CoversPage:
    items: list[CoversItem]
    next_cursor: str | None


def encode_covers_cursor(
    verified_rank: int, tier_rank: int, distance_m: int, last_id: uuid.UUID
) -> str:
    raw = f"{verified_rank}:{tier_rank}:{distance_m}:{last_id.hex}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_covers_cursor(cursor: str) -> tuple[int, int, int, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        parts = base64.urlsafe_b64decode(padded).decode().split(":")
        if len(parts) != 4:  # pre-D26 2-field and pre-M1 3-field cursors land here
            raise ValueError(f"expected 4 fields, got {len(parts)}")
        return int(parts[0]), int(parts[1]), int(parts[2]), uuid.UUID(hex=parts[3])
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

_TIER_RANK = "CASE WHEN b.subscription_tier = 'premium' THEN 0 ELSE 1 END"

# Only 'verified' ranks up. 'pending' sorts with 'unverified' on purpose:
# the D16 admin decision is the sole path to the badge AND to this boost,
# so queueing a claim cannot buy placement (M1 threat model).
_VERIFIED_RANK = "CASE WHEN b.verification_status = 'verified' THEN 0 ELSE 1 END"

_BASE_SQL = f"""
WITH q AS (
    SELECT centroid_lat AS lat, centroid_lon AS lon
    FROM geo.pincodes WHERE pincode = :pincode
)
SELECT b.id, b.name, b.slug, b.type, b.verification_status,
       b.subscription_tier, b.primary_pincode, d.distance_m, nb.lat, nb.lng,
       {_VERIFIED_RANK} AS verified_rank, {_TIER_RANK} AS tier_rank
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
LEFT JOIN LATERAL (
    SELECT br.lat, br.lng
    FROM directory.branches br
    WHERE br.business_id = b.id
      AND br.lat IS NOT NULL AND br.lng IS NOT NULL
      AND br.deleted_at IS NULL
    ORDER BY {_BRANCH_DISTANCE}
    LIMIT 1
) nb ON TRUE
WHERE b.status = 'active' AND b.deleted_at IS NULL
"""

_CURSOR_PREDICATE = f"""
  AND ({_VERIFIED_RANK} > :cursor_verified
       OR ({_VERIFIED_RANK} = :cursor_verified AND {_TIER_RANK} > :cursor_tier)
       OR ({_VERIFIED_RANK} = :cursor_verified AND {_TIER_RANK} = :cursor_tier
           AND d.distance_m > :cursor_distance)
       OR ({_VERIFIED_RANK} = :cursor_verified AND {_TIER_RANK} = :cursor_tier
           AND d.distance_m = :cursor_distance AND b.id > :cursor_id))
"""

_ORDER_LIMIT = "\nORDER BY verified_rank, tier_rank, d.distance_m, b.id\nLIMIT :lim"

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
        cursor_verified, cursor_tier, cursor_distance, cursor_id = decode_covers_cursor(cursor)
        sql += _CURSOR_PREDICATE
        params |= {
            "cursor_verified": cursor_verified,
            "cursor_tier": cursor_tier,
            "cursor_distance": cursor_distance,
            "cursor_id": cursor_id,
        }
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
            lat=m["lat"],
            lng=m["lng"],
        )
        for m in (row._mapping for row in rows[:limit])
    ]
    next_cursor = (
        encode_covers_cursor(
            0 if items[-1].verification_status == "verified" else 1,
            0 if items[-1].subscription_tier == "premium" else 1,
            items[-1].distance_m,
            items[-1].id,
        )
        if len(rows) > limit
        else None
    )
    return CoversPage(items=items, next_cursor=next_cursor)


@dataclass(frozen=True, slots=True)
class NearbyBranch:
    id: uuid.UUID
    address: str
    district: str
    state: str
    pincode: str
    lat: Decimal | None
    lng: Decimal | None
    distance_m: int


MAX_NEARBY_BRANCHES = 10

_BRANCH_PINCODE_DISTANCE = _haversine_m("q.lat", "q.lon", "p.centroid_lat", "p.centroid_lon")

_NEARBY_SQL = f"""
WITH q AS (
    SELECT centroid_lat AS lat, centroid_lon AS lon
    FROM geo.pincodes WHERE pincode = :pincode
)
SELECT br.id, br.address, br.district, br.state, br.pincode, br.lat, br.lng,
       CAST(ROUND(COALESCE(
           CASE WHEN br.lat IS NOT NULL AND br.lng IS NOT NULL
                THEN {_BRANCH_DISTANCE} END,
           (SELECT {_BRANCH_PINCODE_DISTANCE}
            FROM geo.pincodes p WHERE p.pincode = br.pincode),
           {UNLOCATABLE_M}
       )) AS BIGINT) AS distance_m
FROM directory.branches br
JOIN directory.businesses b ON b.id = br.business_id
CROSS JOIN q
WHERE b.slug = :slug AND b.status = 'active' AND b.deleted_at IS NULL
  AND br.deleted_at IS NULL
ORDER BY distance_m, br.id
LIMIT :lim
"""


async def nearby_branches(
    session: AsyncSession, *, slug: str, pincode: str, limit: int = MAX_NEARBY_BRANCHES
) -> list[NearbyBranch]:
    """Brand 'shops near you': this business's branches, nearest first.
    Bounded list, no cursor - brands have bounded branch counts and the
    LIMIT caps the response regardless."""
    rows = (
        await session.execute(
            text(_NEARBY_SQL),
            {"slug": slug, "pincode": pincode, "lim": min(limit, MAX_NEARBY_BRANCHES)},
        )
    ).all()
    return [
        NearbyBranch(
            id=m["id"],
            address=m["address"],
            district=m["district"],
            state=m["state"],
            pincode=m["pincode"],
            lat=m["lat"],
            lng=m["lng"],
            distance_m=int(m["distance_m"]),
        )
        for m in (row._mapping for row in rows)
    ]
