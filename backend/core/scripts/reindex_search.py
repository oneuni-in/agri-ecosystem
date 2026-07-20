"""Rebuild search indexes: republish every business/product's snapshot over
the "directory" event stream (ADR-0007 "indexes are rebuildable" - Meilisearch
holds no truth of its own, so recovering from a wiped/corrupted index, or
backfilling after a search-worker outage, is just re-emitting every row's
current snapshot and letting the worker (D19 Task 3) replay its normal
apply-event logic).

Every id is republished - including soft-deleted/pending/suspended rows -
so the worker also tombstones documents for anything that is no longer
publicly visible, not just re-index what's currently visible.

Run: python -m scripts.reindex_search   (the search worker must be running,
or events queue in the stream until it next consumes).
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.catalog_models import Product
from modules.directory.models import Business
from modules.directory.search_sync import business_event_payload, product_event_payload
from shared.db import get_sessionmaker
from shared.events import publish
from shared.telemetry import get_logger

STREAM = "directory"

logger = get_logger(__name__)


async def run(session: AsyncSession) -> int:
    """Republish one business.updated/product.updated event per row (visible
    or not); returns the total number of events published."""
    count = 0
    for biz_id in (
        await session.execute(select(Business.id).execution_options(include_deleted=True))
    ).scalars():
        await publish(STREAM, "business.updated", await business_event_payload(session, biz_id))
        count += 1
    for prod_id in (
        await session.execute(select(Product.id).execution_options(include_deleted=True))
    ).scalars():
        await publish(STREAM, "product.updated", await product_event_payload(session, prod_id))
        count += 1
    return count


async def main() -> None:
    async with get_sessionmaker()() as session:
        count = await run(session)
    logger.info("reindex_search: republished snapshots", extra={"extra_fields": {"count": count}})
    print(f"republished {count} search events")  # noqa: T201 - CLI output


if __name__ == "__main__":
    asyncio.run(main())
