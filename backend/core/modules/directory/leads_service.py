"""Leads engine service (D18.B): routing, ownership, stats.

Routing rule (locked by plan): an explicit business_id must cover the
pincode (else BusinessNotCoveredError - non-negotiable 4); no business_id
means nearest covering business wins (covers() distance order), category-
filtered when given. One inquiry -> one inbox; no fan-out (guest-spam
amplification).

AUTO-routing (business_id=None) requires the searched pincode to resolve
in geo.pincodes to establish a distance anchor for covers(); if the pincode
is not geocoded, covers() returns zero rows and NoCoverageError is raised
even if covering businesses exist. Explicit business_id routing checks
business_coverage directly and does not require a geo.pincodes entry."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.covers import covers
from modules.directory.leads_models import Inquiry, PincodeInterest
from modules.directory.models import Business
from modules.directory.service import BusinessNotFoundError, get_owned_business
from shared.geo.service import district_for_pincode


class LeadsError(Exception):
    pass


class BusinessNotCoveredError(LeadsError):
    pass


class NoCoverageError(LeadsError):
    pass


class InquiryNotFoundError(LeadsError):
    pass


@dataclass(frozen=True, slots=True)
class RoutedBusiness:
    id: uuid.UUID
    name: str
    owner_user_id: uuid.UUID | None


_COVERED_SQL = text(
    """
    SELECT b.id, b.name, b.owner_user_id
    FROM directory.businesses b
    JOIN directory.business_coverage c
      ON c.business_id = b.id AND c.pincode = :pincode
    WHERE b.id = :business_id AND b.status = 'active' AND b.deleted_at IS NULL
    """
)


async def route_inquiry(
    session: AsyncSession,
    *,
    pincode: str,
    category: str | None,
    business_id: uuid.UUID | None,
) -> RoutedBusiness:
    """Route an inquiry to a covering business.

    Raises NoCoverageError if auto-routing and either the pincode is not
    geocoded in geo.pincodes (needed for distance ordering) or no covering
    business exists in the searched pincode."""
    if business_id is not None:
        row = (
            await session.execute(_COVERED_SQL, {"pincode": pincode, "business_id": business_id})
        ).first()
        if row is None:
            raise BusinessNotCoveredError(str(business_id))
        m = row._mapping
        return RoutedBusiness(id=m["id"], name=m["name"], owner_user_id=m["owner_user_id"])
    page = await covers(session, pincode=pincode, limit=1, category=category)
    if not page.items:
        raise NoCoverageError(pincode)
    nearest = page.items[0]
    owner = await session.scalar(select(Business.owner_user_id).where(Business.id == nearest.id))
    return RoutedBusiness(id=nearest.id, name=nearest.name, owner_user_id=owner)


async def get_owned_inquiry(
    session: AsyncSession, owner_user_id: uuid.UUID, inquiry_id: uuid.UUID
) -> Inquiry:
    """Fetch an inquiry, but only if the caller owns its business.

    IDOR contract: someone else's inquiry and a missing one are the SAME 404
    (mirrors get_owned_business's own not-yours-is-missing rule)."""
    inquiry = await session.scalar(select(Inquiry).where(Inquiry.id == inquiry_id))
    if inquiry is None:
        raise InquiryNotFoundError(str(inquiry_id))
    try:
        await get_owned_business(session, owner_user_id, inquiry.business_id)
    except BusinessNotFoundError:
        raise InquiryNotFoundError(str(inquiry_id)) from None
    return inquiry


_STATS_SQL = text(
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
    WHERE i.business_id = :business_id
    """
)


async def inbox_stats(session: AsyncSession, business_id: uuid.UUID) -> tuple[int, int, int | None]:
    """Aggregate response-time stats for one business's inbox.

    avg(...) over the lateral join averages only rows where first_at is
    non-NULL - SQL avg ignores NULLs - which is the intended "response-time
    stat over responded inquiries"."""
    row = (await session.execute(_STATS_SQL, {"business_id": business_id})).one()
    m = row._mapping
    avg = m["avg_response_seconds"]
    return int(m["total"]), int(m["responded"]), int(avg) if avg is not None else None


async def record_pincode_interest(
    session: AsyncSession,
    *,
    pincode: str,
    contact: str | None,
    milk_type: str | None,
    from_user_id: uuid.UUID | None,
) -> PincodeInterest:
    """Persist a warm-empty-state demand row. Derives district from geo when
    the pincode is TN (non-TN → district stays None). No coverage routing —
    this row exists BECAUSE there is no covering vendor."""
    district = await district_for_pincode(session, pincode)
    row = PincodeInterest(
        pincode=pincode,
        district=district.name if district is not None else None,
        contact=contact,
        milk_type=milk_type,
        from_user_id=from_user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def record_reveal_inquiry(
    session: AsyncSession, *, user_id: uuid.UUID, business_id: uuid.UUID, pincode: str
) -> Inquiry | None:
    """Attribution lead for a contact reveal (D24.B): the reveal IS a contact
    intent, so it lands in the vendor inbox / response stats like any lead.
    Deduped per (user, business, UTC day) so repeat reveals don't spam the
    inbox. Direct insert, NOT route_inquiry(): the business is already known
    and its branch pincode may legitimately sit outside its coverage list.
    The payload must never carry the revealed number (DPDP)."""
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    existing = await session.scalar(
        select(Inquiry.id).where(
            Inquiry.from_user_id == user_id,
            Inquiry.business_id == business_id,
            Inquiry.type == "contact",
            Inquiry.payload["source"].astext == "contact_reveal",
            Inquiry.created_at >= midnight,
        )
    )
    if existing is not None:
        return None
    inquiry = Inquiry(
        type="contact",
        from_user_id=user_id,
        business_id=business_id,
        payload={
            "message": "Contact number revealed via profile page.",
            "source": "contact_reveal",
        },
        pincode=pincode,
    )
    session.add(inquiry)
    await session.flush()
    return inquiry
