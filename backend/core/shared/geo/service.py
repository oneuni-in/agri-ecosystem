"""Geo lookups used by module services."""

from decimal import Decimal

from sqlalchemy import select, text
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


async def nearest_pincode(session: AsyncSession, lat: float, lon: float) -> Pincode | None:
    """Full-scan haversine nearest-neighbour over geo.pincodes (~2k TN rows;
    no PostGIS needed at this volume - same integer-metre idiom as
    modules/directory/covers.py's _haversine_m)."""
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    row = await session.execute(
        text("""
            SELECT id FROM geo.pincodes
            ORDER BY 2 * 6371000 * asin(sqrt(
                power(sin(radians((centroid_lat - :lat) / 2)), 2)
                + cos(radians(:lat)) * cos(radians(centroid_lat))
                * power(sin(radians((centroid_lon - :lon) / 2)), 2)))
            LIMIT 1
        """),
        {"lat": lat, "lon": lon},
    )
    pk = row.scalar()
    return await session.get(Pincode, pk) if pk else None
