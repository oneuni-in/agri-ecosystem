"""Billing dunning worker (D20): a pure timer loop - it consumes no streams.
Run: python -m modules.billing.worker (standalone, coins-worker precedent).
Each tick advances the dunning machine (modules/billing/service.py) for due
past_due subscriptions. No-ops while billing_worker_enabled is false or the
billing_enabled flag is off - zero reads, zero live calls while dark.
Never logs payloads; ids only."""

import asyncio
import contextlib
from datetime import UTC, datetime

from modules.billing import razorpay_client
from modules.billing.service import publish_pending, run_due_dunning
from settings import get_settings
from shared.db import get_sessionmaker
from shared.flags import flag_enabled
from shared.telemetry import get_logger

logger = get_logger(__name__)

POLL_INTERVAL_SECONDS = 300.0


async def worker_tick(*, now: datetime | None = None) -> int:
    settings = get_settings()
    if not settings.billing_worker_enabled:
        return 0
    async with get_sessionmaker()() as session:
        if not await flag_enabled("billing_enabled", session=session):
            return 0
        processed, pending = await run_due_dunning(
            session,
            now=now or datetime.now(UTC),
            client=razorpay_client.get_client(),
            settings=settings,
        )
        await session.commit()
    await publish_pending(pending)
    return processed


async def run_worker(stop: asyncio.Event, *, poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
    logger.info("billing worker started")
    while not stop.is_set():
        try:
            processed = await worker_tick()
            if processed:
                logger.info(
                    "billing.dunning_tick", extra={"extra_fields": {"processed": processed}}
                )
        except Exception as exc:  # a DB/redis blip must not kill the loop
            logger.warning(
                "billing.worker_tick_failed",
                extra={"extra_fields": {"exc_type": type(exc).__name__}},
            )
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=poll_interval)
    logger.info("billing worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker(asyncio.Event()))
