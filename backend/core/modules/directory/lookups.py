"""Directory's lookup adapters for shared.lookups (D20). Registered by
main.create_app(); the only sanctioned way another module learns who owns a
business."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.models import Business
from shared.lookups import BusinessRef


def _ref(business: Business) -> BusinessRef:
    return BusinessRef(id=business.id, owner_user_id=business.owner_user_id, name=business.name)


async def business_ref(session: AsyncSession, business_id: uuid.UUID) -> BusinessRef | None:
    business = await session.scalar(select(Business).where(Business.id == business_id))
    return _ref(business) if business is not None else None


async def business_is_servable(session: AsyncSession, business_id: uuid.UUID) -> bool:
    """M1.5.E status accessor for shared.lookups.is_servable: may this
    business be shown/served anywhere (ads included)? Only status='active'
    qualifies; unknown or soft-deleted rows answer False (fail closed).
    Soft-deleted rows are filtered by the ORM listener already."""
    status = await session.scalar(select(Business.status).where(Business.id == business_id))
    return status == "active"


async def owned_business_refs(session: AsyncSession, owner_user_id: uuid.UUID) -> list[BusinessRef]:
    businesses = (
        await session.scalars(
            select(Business).where(Business.owner_user_id == owner_user_id).order_by(Business.id)
        )
    ).all()
    return [_ref(business) for business in businesses]
