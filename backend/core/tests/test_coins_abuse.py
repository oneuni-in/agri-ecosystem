"""Clustering: many referees sharing a device fingerprint or phone prefix under
one referrer raise abuse flags for admin review."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import abuse, referrals
from modules.coins.models import AbuseFlag

pytestmark = pytest.mark.asyncio


async def _seed(
    session: AsyncSession,
    referrer: uuid.UUID,
    n: int,
    *,
    fp: str | None = None,
    prefix: str | None = None,
) -> None:
    code = await referrals.get_or_create_code(session, referrer)
    for _ in range(n):
        await referrals.attribute(
            session,
            referee_id=uuid.uuid4(),
            code=code,
            device_fingerprint=fp,
            phone_prefix=prefix,
        )


async def test_device_cluster_flags(db_session: AsyncSession) -> None:
    referrer = uuid.uuid4()
    await _seed(db_session, referrer, 3, fp="DEVICE-XYZ")
    flags = await abuse.scan_clusters(db_session, min_cluster=3)
    assert len(flags) >= 3
    assert all(f.cluster_reason == "device" for f in flags)


async def test_below_threshold_no_flag(db_session: AsyncSession) -> None:
    await _seed(db_session, uuid.uuid4(), 2, fp="DEVICE-Q")
    assert await abuse.scan_clusters(db_session, min_cluster=3) == []


async def test_scan_is_idempotent(db_session: AsyncSession) -> None:
    referrer = uuid.uuid4()
    await _seed(db_session, referrer, 3, prefix="9198")
    await abuse.scan_clusters(db_session, min_cluster=3)
    await abuse.scan_clusters(db_session, min_cluster=3)
    count = await db_session.scalar(select(func.count()).select_from(AbuseFlag))
    assert count == 3  # not doubled
