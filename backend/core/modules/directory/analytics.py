"""Analytics-lite (D26.D): profile-view recording + dashboard aggregates.

Views are DPDP-minimal by construction: the beacon stores a daily-rotating
viewer pseudonym (ads-module precedent), never IP/UA, and the table is
append-only by grant. Dedupe (1 view/viewer/business/UTC-day) is the DB
unique index - the hash itself rotates daily, so (business_id, viewer_hash)
is day-scoped without any Redis state."""

import hashlib
import uuid
from datetime import datetime

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
