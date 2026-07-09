"""Geo lookups used by module services."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.geo.models import District, Pincode


async def district_for_pincode(session: AsyncSession, pincode: str) -> District | None:
    result = await session.scalars(
        select(District)
        .join(Pincode, Pincode.district_id == District.id)
        .where(Pincode.pincode == pincode)
    )
    return result.first()


async def centroid_for_pincode(
    session: AsyncSession, pincode: str
) -> tuple[Decimal, Decimal] | None:
    row = (
        await session.execute(
            select(Pincode.centroid_lat, Pincode.centroid_lon).where(Pincode.pincode == pincode)
        )
    ).first()
    if row is None:
        return None
    return (row.centroid_lat, row.centroid_lon)
