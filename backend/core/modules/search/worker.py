"""Search event worker (D19) - standalone consumer of the "directory" stream
that turns business.*/product.* fat events into Meilisearch upsert/delete
calls (modules.search.indexing.apply_event).

Payloads are self-contained (ADR-0007 fat events): this worker needs NO DB
session and must never import modules.directory - the owning module is the
only builder of index-worthy snapshots.

Run: python -m modules.search.worker
Never log event payloads (search must not index/log private fields).
"""

import asyncio

from shared.events import EventConsumer
from shared.telemetry import get_logger

from .indexing import apply_event, ensure_indexes

logger = get_logger(__name__)

STREAMS = ("directory",)
GROUP = "search"
NAME = "search-worker-1"


async def process_once(consumers: list[EventConsumer], *, count: int = 50) -> bool:
    """One pass over every consumer: reap poison, read, apply, ack.

    Returns whether any work was done, so run()'s idle-sleep and tests share
    this single code path (see docstring on the module for the contract).
    """
    did_work = False
    for consumer in consumers:
        await consumer.reap_poison()
        events = await consumer.read(count=count)
        if events:
            did_work = True
        for event in events:
            try:
                await apply_event(event)
                await consumer.ack(event)
            except Exception:
                logger.exception(
                    "search worker: event failed; left unacked, no retry path",
                    extra={"extra_fields": {"event_type": event.type}},
                )
                # No ack -> the event stays in this consumer's PEL, but there
                # is no safety net behind that: EventConsumer.read only reads
                # `>` (new messages), with no XAUTOCLAIM/idle-sweep of the
                # PEL, so times_delivered never increments and reap_poison
                # never claims it. The event is simply lost - not redelivered,
                # not DLQ'd, not alerted on - until an operator notices and
                # runs scripts/reindex_search.py. Implementing a redelivery
                # sweep is out of scope here (shared-bus concern, see
                # modules/coins/worker.py's identical limitation).
    return did_work


async def run() -> None:  # pragma: no cover - exercised via integration, not unit
    consumers = [EventConsumer(stream, group=GROUP, name=NAME) for stream in STREAMS]
    for consumer in consumers:
        await consumer.ensure_group()
    await ensure_indexes()
    logger.info(
        "search worker started",
        extra={"extra_fields": {"streams": list(STREAMS), "group": GROUP}},
    )
    while True:
        did_work = await process_once(consumers)
        if not did_work:
            await asyncio.sleep(0.5)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run())
