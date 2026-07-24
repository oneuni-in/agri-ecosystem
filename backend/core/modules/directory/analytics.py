"""Analytics-lite (D26.D): profile-view recording + dashboard aggregates.

Views are DPDP-minimal by construction: the beacon stores a daily-rotating
viewer pseudonym (ads-module precedent), never IP/UA, and the table is
append-only by grant. Dedupe (1 view/viewer/business/UTC-day) is the DB
unique index - the hash itself rotates daily, so (business_id, viewer_hash)
is day-scoped without any Redis state."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import TextClause, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.models import ProfileView
from settings import get_settings


def viewer_hash(ip: str, user_agent: str, *, now: datetime) -> str:
    secret = get_settings().view_beacon_secret
    raw = f"{secret}:{now:%Y%m%d}:{ip}:{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def record_view(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    pincode: str | None,
    viewer_hash_value: str,
    now: datetime,
) -> None:
    await session.execute(
        pg_insert(ProfileView)
        .values(
            business_id=business_id,
            pincode=pincode,
            viewer_hash=viewer_hash_value,
            occurred_at=now,
        )
        .on_conflict_do_nothing(index_elements=["business_id", "viewer_hash"])
    )


_BY_PINCODE_LIMIT = 20

_VIEWS_SQL = text(
    """
    SELECT COALESCE(pincode, 'unknown') AS pincode, count(*) AS count
    FROM directory.profile_views
    WHERE business_id = :business_id AND occurred_at >= :since
    GROUP BY 1 ORDER BY count DESC, pincode ASC LIMIT :lim
    """
)
_VIEWS_TOTAL_SQL = text(
    """
    SELECT count(*) FROM directory.profile_views
    WHERE business_id = :business_id AND occurred_at >= :since
    """
)
# reveal-attribution rows are inquiries with payload.source == 'contact_reveal'
# (leads_service.record_reveal_inquiry); everything else in the inbox is a
# real lead (direct contact + need fan-out children alike).
_INQUIRY_SQL = text(
    """
    SELECT COALESCE(pincode, 'unknown') AS pincode, count(*) AS count
    FROM leads.inquiries
    WHERE business_id = :business_id AND created_at >= :since
      AND (payload->>'source' IS NOT DISTINCT FROM 'contact_reveal') = :is_reveal
    GROUP BY 1 ORDER BY count DESC, pincode ASC LIMIT :lim
    """
)
_INQUIRY_TOTAL_SQL = text(
    """
    SELECT count(*) FROM leads.inquiries
    WHERE business_id = :business_id AND created_at >= :since
      AND (payload->>'source' IS NOT DISTINCT FROM 'contact_reveal') = :is_reveal
    """
)
_RESPONSE_SQL = text(
    """
    SELECT
        count(*) AS total,
        count(*) FILTER (WHERE i.status <> 'new') AS responded,
        CAST(avg(EXTRACT(EPOCH FROM fr.first_at - i.created_at)) AS BIGINT)
            AS avg_response_seconds
    FROM leads.inquiries i
    LEFT JOIN LATERAL (
        SELECT min(r.created_at) AS first_at
        FROM leads.responses r WHERE r.inquiry_id = i.id
    ) fr ON true
    WHERE i.business_id = :business_id AND i.created_at >= :since
    """
)


@dataclass(frozen=True, slots=True)
class PincodeCount:
    pincode: str
    count: int


@dataclass(frozen=True, slots=True)
class Section:
    total: int
    by_pincode: list[PincodeCount]


@dataclass(frozen=True, slots=True)
class ResponseStats:
    total: int
    responded: int
    avg_response_seconds: int | None


@dataclass(frozen=True, slots=True)
class AnalyticsData:
    views: Section
    reveals: Section
    leads: Section
    response: ResponseStats


async def _section(
    session: AsyncSession, total_sql: TextClause, by_sql: TextClause, params: dict[str, object]
) -> Section:
    total = int(await session.scalar(total_sql, params) or 0)
    rows = (await session.execute(by_sql, {**params, "lim": _BY_PINCODE_LIMIT})).all()
    return Section(
        total=total,
        by_pincode=[
            PincodeCount(pincode=m["pincode"], count=int(m["count"]))
            for m in (row._mapping for row in rows)
        ],
    )


async def business_analytics(
    session: AsyncSession, *, business_id: uuid.UUID, since: datetime
) -> AnalyticsData:
    base = {"business_id": business_id, "since": since}
    views = await _section(session, _VIEWS_TOTAL_SQL, _VIEWS_SQL, base)
    reveals = await _section(session, _INQUIRY_TOTAL_SQL, _INQUIRY_SQL, {**base, "is_reveal": True})
    leads = await _section(session, _INQUIRY_TOTAL_SQL, _INQUIRY_SQL, {**base, "is_reveal": False})
    row = (await session.execute(_RESPONSE_SQL, base)).one()._mapping
    avg = row["avg_response_seconds"]
    return AnalyticsData(
        views=views,
        reveals=reveals,
        leads=leads,
        response=ResponseStats(
            total=int(row["total"]),
            responded=int(row["responded"]),
            avg_response_seconds=int(avg) if avg is not None else None,
        ),
    )
