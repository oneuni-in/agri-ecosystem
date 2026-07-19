"""Leads engine service (D18.B): routing, ownership, stats.

Routing rule (locked by plan): an explicit business_id must cover the
pincode (else BusinessNotCoveredError - non-negotiable 4); no business_id
means nearest covering business wins (covers() distance order), category-
filtered when given. One inquiry -> one inbox; no fan-out (guest-spam
amplification)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.covers import covers
from modules.directory.models import Business


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
