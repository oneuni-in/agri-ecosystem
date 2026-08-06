"""Ads maintenance worker (D21): a pure timer loop (billing-worker precedent).
Run: python -m modules.ads.worker. Each tick pre-creates upcoming daily
partitions via the ADMIN engine. Deliberately NOT gated on the ads_enabled DB
flag: partitions must exist before the flag ever flips (serve/beacons 404
while dark anyway); any future serving-related tick work MUST check the flag.

M5 Task 7: each tick also durably sweeps the two derived lifecycle states
(active -> expired/exhausted, lifecycle.sweep_lifecycle) through the app
engine (shared.db.get_sessionmaker), not the admin engine used for
partitions - lifecycle rows are ordinary app_rt-owned data.

Never logs payloads; names/counts only."""

import asyncio
import contextlib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import create_async_engine

from modules.ads import lifecycle
from modules.ads.maintenance import ensure_partitions
from settings import get_settings
from shared.db import get_sessionmaker
from shared.telemetry import get_logger

logger = get_logger(__name__)

POLL_INTERVAL_SECONDS = 21600.0  # 6h


async def worker_tick(*, now: datetime | None = None) -> int:
    settings = get_settings()
    if not settings.ads_worker_enabled:
        return 0
    today = (now or datetime.now(UTC)).date()
    engine = create_async_engine(settings.database_admin_url)
    try:
        async with engine.begin() as conn:
            created = await ensure_partitions(conn, start=today, days_ahead=7)
    finally:
        await engine.dispose()
    async with get_sessionmaker()() as session:
        await lifecycle.sweep_lifecycle(session, today=today)
        await session.commit()
    return len(created)


async def run_worker(stop: asyncio.Event, *, poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
    logger.info("ads worker started")
    while not stop.is_set():
        try:
            created = await worker_tick()
            if created:
                logger.info("ads.partitions_created", extra={"extra_fields": {"count": created}})
        except Exception as exc:  # a DB blip must not kill the loop
            logger.warning(
                "ads.worker_tick_failed",
                extra={"extra_fields": {"exc_type": type(exc).__name__}},
            )
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=poll_interval)
    logger.info("ads worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker(asyncio.Event()))
