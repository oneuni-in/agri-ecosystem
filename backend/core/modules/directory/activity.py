""" "Live on agri.in" activity recorder + reader (A-U4b O11).

THE PRIVACY CONTRACT IS THE SCHEMA (models.Activity, migration 0051): the
table has no user id, no person's name, no pincode and no contact column,
so a hook physically cannot leak what the schema cannot hold.

record_activity never commits - the caller owns the transaction - and can
never poison it: the insert runs inside a SAVEPOINT (coins record_entry
precedent), so a duplicate (kind, source_id) rolls back only that insert
(DB-proven idempotency, UNIQUE(kind, source_id)), and ANY other failure is
logged and swallowed. The feed is decoration; the domain write is the
point.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.models import Activity
from shared.geo.models import State
from shared.geo.service import district_for_pincode

logger = logging.getLogger(__name__)

FEED_WINDOW_HOURS = 24
FEED_LIMIT = 30


async def record_activity(
    session: AsyncSession,
    *,
    kind: str,
    source_id: uuid.UUID,
    occurred_at: datetime,
    district: str | None = None,
    state: str | None = None,
    business_name: str | None = None,
    business_slug: str | None = None,
    rating: int | None = None,
) -> None:
    """Best-effort insert of one feed row in the CALLER's transaction.

    Duplicates (same kind + source_id) are a silent no-op - that is the
    idempotency contract, e.g. claim approval and verification approval
    both announcing 'business_joined' for one business. Unexpected errors
    are logged and swallowed: an activity row must never fail the domain
    write it decorates.
    """
    savepoint = await session.begin_nested()
    try:
        session.add(
            Activity(
                kind=kind,
                occurred_at=occurred_at,
                source_id=source_id,
                district=district,
                state=state,
                business_name=business_name,
                business_slug=business_slug,
                rating=rating,
            )
        )
        await session.flush()  # UNIQUE(kind, source_id) fires here on replay
    except IntegrityError:
        await savepoint.rollback()  # already recorded - DB-proven idempotency
    except Exception:
        await savepoint.rollback()
        logger.warning("activity: insert failed", extra={"extra_fields": {"kind": kind}})


async def location_for_pincode(
    session: AsyncSession, pincode: str
) -> tuple[str | None, str | None]:
    """(district, state) display names for a pincode - COARSE location for a
    feed row. (None, None) when the pincode is not geocoded (non-TN until
    D65): the location is omitted, never guessed, and the pincode itself is
    resolved here and DROPPED - it never reaches the activity table."""
    district = await district_for_pincode(session, pincode)
    if district is None:
        return None, None
    state = await session.scalar(select(State.name).where(State.id == district.state_id))
    return district.name, state


async def recent_activity(
    session: AsyncSession, *, window_hours: int = FEED_WINDOW_HOURS, limit: int = FEED_LIMIT
) -> list[Activity]:
    """Newest-first feed rows within the window. Fixed window + limit, no
    cursor: a marquee reads the last N and there is no page 2 (documented
    on the route)."""
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    rows = await session.scalars(
        select(Activity)
        .where(Activity.occurred_at >= since)
        .order_by(Activity.occurred_at.desc(), Activity.id.desc())
        .limit(limit)
    )
    return list(rows)
