"""In-process notify worker (D12): consume events, retry due deliveries,
reap poison messages to the bus DLQ. Started from main.py's lifespan when
settings.notify_worker_enabled; tests call handle_event/retry_due_deliveries
directly and never run this loop."""

import asyncio
import contextlib

from modules.notify.consumers import CONSUMER_GROUP, STREAMS, handle_event
from modules.notify.service import retry_due_deliveries
from shared.db import get_sessionmaker
from shared.events import EventConsumer
from shared.telemetry import get_logger

logger = get_logger(__name__)


async def run_worker(stop: asyncio.Event, *, poll_interval: float = 2.0) -> None:
    consumers = [
        EventConsumer(stream, group=CONSUMER_GROUP, name="notify-worker") for stream in STREAMS
    ]
    for consumer in consumers:
        await consumer.ensure_group()
    logger.info("notify worker started")
    while not stop.is_set():
        try:
            for consumer in consumers:
                for event in await consumer.read(count=10):
                    try:
                        async with get_sessionmaker()() as session:
                            await handle_event(session, event)
                            await session.commit()
                        await consumer.ack(event)
                    except Exception as exc:
                        # unacked -> redelivered; >= max_deliveries -> :dlq
                        logger.warning(
                            "notify.event_failed",
                            extra={
                                "extra_fields": {
                                    "event_type": event.type,
                                    "exc_type": type(exc).__name__,
                                }
                            },
                        )
                await consumer.reap_poison()
            async with get_sessionmaker()() as session:
                await retry_due_deliveries(session)
                await session.commit()
        except Exception as exc:  # a redis blip must not kill the loop
            logger.warning(
                "notify.worker_tick_failed",
                extra={"extra_fields": {"exc_type": type(exc).__name__}},
            )
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=poll_interval)
    logger.info("notify worker stopped")
