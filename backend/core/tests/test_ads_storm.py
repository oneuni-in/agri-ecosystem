"""Concurrent beacon storm (D21, slow suite): N concurrent impression inserts
across the day-boundary window - zero lost inserts, zero errors, rows land in
the right partitions. Run: python -m pytest tests/test_ads_storm.py -m slow"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from modules.ads import service
from modules.ads.models import Campaign, Impression, Placement

pytestmark = pytest.mark.asyncio

N = 2_000
CONCURRENCY = 16  # bound simultaneous connections; asyncio queues the rest


@pytest.mark.slow
async def test_storm_beacon_inserts_across_day_boundary(database_url: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    campaign_id = uuid.uuid4()
    placement_id = uuid.uuid4()
    creative_id = uuid.uuid4()

    now = datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=1, microsecond=0)

    sem = asyncio.Semaphore(CONCURRENCY)

    async def insert(i: int) -> None:
        occurred_at = now if i % 2 == 0 else tomorrow
        async with sem, maker() as s:
            s.add(
                Impression(
                    id=uuid.uuid4(),
                    placement_id=placement_id,
                    creative_id=creative_id,
                    slot_key="directory_browse",
                    viewer_hash=f"vh-{i}",
                    pincode="641001",
                    occurred_at=occurred_at,
                )
            )
            await s.commit()

    try:
        # seed one placement (real committing rows - the storm engine below
        # sees them since both connect against the same test DB)
        async with maker() as s:
            s.add(
                Campaign(
                    id=campaign_id,
                    advertiser_business_id=uuid.uuid4(),
                    name="storm campaign",
                    status="active",
                    budget_display="",
                    flight_start=now.date(),
                    flight_end=tomorrow.date(),
                )
            )
            s.add(
                Placement(
                    id=placement_id,
                    campaign_id=campaign_id,
                    slot_key="directory_browse",
                    geo_target={},
                    weight=1,
                    status="active",
                )
            )
            await s.commit()

        await asyncio.gather(*(insert(i) for i in range(N)))

        async with maker() as s:
            count = await s.scalar(
                text("SELECT count(*) FROM ads.impressions WHERE placement_id = :p"),
                {"p": placement_id},
            )
            partitions = (
                (
                    await s.execute(
                        text(
                            "SELECT DISTINCT tableoid::regclass::text FROM ads.impressions "
                            "WHERE placement_id = :p"
                        ),
                        {"p": placement_id},
                    )
                )
                .scalars()
                .all()
            )

        assert count == N, "lost inserts under concurrency"
        today_partition = f"ads.impressions_p{now:%Y%m%d}"
        tomorrow_partition = f"ads.impressions_p{tomorrow:%Y%m%d}"
        assert set(partitions) == {today_partition, tomorrow_partition}, (
            "rows did not land in the two expected daily partitions"
        )
    finally:
        # impressions is append-only (grant + trigger) so there is nothing to
        # clean up; the agri_test DB is dropped and recreated once per
        # session (conftest.database_url).
        await engine.dispose()


@pytest.mark.slow
async def test_budget_race_never_oversells(database_url: str) -> None:
    """M3 threat model: concurrent serves must never spend more credits than
    exist. 100 racers against 50 credits -> exactly 50 winners, used == 50."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    campaign_id = uuid.uuid4()
    today = datetime.now(UTC).date()
    sem = asyncio.Semaphore(CONCURRENCY)

    async def spend() -> bool:
        async with sem, maker() as s:
            campaign = await s.get(Campaign, campaign_id)
            assert campaign is not None
            ok = await service.consume_budget(s, campaign)
            await s.commit()
            return ok

    try:
        async with maker() as s:
            s.add(
                Campaign(
                    id=campaign_id,
                    advertiser_business_id=uuid.uuid4(),
                    name="budget race",
                    status="active",
                    budget_display="",
                    budget_serves_total=50,
                    flight_start=today,
                    flight_end=today,
                )
            )
            await s.commit()

        results = await asyncio.gather(*(spend() for _ in range(100)))
        assert sum(results) == 50, "conditional UPDATE let a credit be spent twice"

        async with maker() as s:
            used = await s.scalar(
                text("SELECT budget_serves_used FROM ads.campaigns WHERE id = :c"),
                {"c": campaign_id},
            )
        assert used == 50
    finally:
        await engine.dispose()
