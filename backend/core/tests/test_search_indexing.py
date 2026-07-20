"""D19 Task 3: event-driven indexer (apply_event) + standalone worker.

Integration tests hit the REAL Meilisearch dev instance (see the `meili`
fixture, ADR-0007) - no mocking of the Meili HTTP API. The worker test also
needs a real (test) Redis stream - see the `bus_redis` fixture, mirroring
tests/test_events.py.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from redis.asyncio import Redis

from modules.search import indexing
from modules.search.client import get_meili
from modules.search.worker import GROUP, STREAMS, process_once
from settings import get_settings
from shared.cache import reset_redis
from shared.events import Event, EventConsumer, publish
from tests.conftest import TEST_REDIS_DB

pytestmark = pytest.mark.asyncio

BIZ_SNAP: dict[str, Any] = {  # copy of a realistic Task-1 snapshot
    "id": "business_cafe0001",
    "kind": "business",
    "sites": ["agri", "milk"],
    "name": "Kovai Dairy",
    "slug": "kovai-dairy",
    "description": None,
    "categories": ["dairy"],
    "district": "Coimbatore",
    "state": "Tamil Nadu",
    "covered_pincodes": ["641001"],
    "verified": False,
    "_geo": {"lat": 11.0, "lng": 76.9},
}


@pytest.fixture
async def bus_redis(redis_client: Redis, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Redis]:
    """Point the bus's own client at the flushed test redis DB (mirrors
    tests/test_events.py) - the worker test publishes/consumes for real."""
    url = get_settings().redis_url.rsplit("/", 1)[0] + f"/{TEST_REDIS_DB}"
    monkeypatch.setenv("REDIS_URL", url)
    get_settings.cache_clear()
    reset_redis()
    yield redis_client


async def test_sites_tuple_matches_directory_search_sync() -> None:
    """indexing.SITES is a deliberate, by-hand copy of
    modules/directory/search_sync.py's SITES (module independence forbids
    modules/search from importing modules/directory in application code) -
    this is the trip-wire that catches drift between the two. Importing
    modules.directory from a *test* is not an import-linter violation; only
    modules/search's own source is contract-checked."""
    from modules.directory import search_sync

    assert indexing.SITES == search_sync.SITES


async def test_upsert_on_snapshot(meili: None) -> None:
    await indexing.ensure_indexes()
    await indexing.apply_event(
        Event(
            id="1-1",
            type="business.created",
            payload={"business_id": "x", "doc_id": "business_cafe0001", "snapshot": BIZ_SNAP},
        )
    )
    for site in ("agri", "milk"):
        res = await get_meili().search(indexing.index_uid(site), {"q": "kovai"})
        assert any(h["id"] == "business_cafe0001" for h in res["hits"])


async def test_delete_on_null_snapshot(meili: None) -> None:
    await indexing.ensure_indexes()
    await indexing.apply_event(
        Event(
            id="1-1",
            type="business.created",
            payload={"business_id": "x", "doc_id": "business_cafe0001", "snapshot": BIZ_SNAP},
        )
    )
    await indexing.apply_event(
        Event(
            id="1-2",
            type="business.updated",
            payload={"business_id": "x", "snapshot": None, "doc_id": "business_cafe0001"},
        )
    )
    for site in ("agri", "milk"):
        res = await get_meili().search(indexing.index_uid(site), {"q": "kovai"})
        assert not any(h["id"] == "business_cafe0001" for h in res["hits"])


async def test_site_narrowing_removes_from_dropped_site(meili: None) -> None:
    """snapshot loses "milk" from sites -> deleted from search_milk, kept in search_agri."""
    await indexing.ensure_indexes()
    await indexing.apply_event(
        Event(
            id="1-1",
            type="business.created",
            payload={"business_id": "x", "doc_id": "business_cafe0001", "snapshot": BIZ_SNAP},
        )
    )
    narrowed = {**BIZ_SNAP, "sites": ["agri"]}
    await indexing.apply_event(
        Event(
            id="1-2",
            type="business.updated",
            payload={"business_id": "x", "doc_id": "business_cafe0001", "snapshot": narrowed},
        )
    )
    agri_res = await get_meili().search(indexing.index_uid("agri"), {"q": "kovai"})
    assert any(h["id"] == "business_cafe0001" for h in agri_res["hits"])
    milk_res = await get_meili().search(indexing.index_uid("milk"), {"q": "kovai"})
    assert not any(h["id"] == "business_cafe0001" for h in milk_res["hits"])


async def test_unknown_event_types_ignored(meili: None) -> None:
    await indexing.apply_event(Event(id="1-3", type="lead.created", payload={}))  # no raise


async def test_malformed_event_missing_doc_id_is_dropped_not_raised(meili: None) -> None:
    """No doc_id anywhere (top-level) -> the indexer cannot key a delete;
    drop and log rather than raise (an unacked event stalls the stream)."""
    await indexing.apply_event(
        Event(id="1-4", type="business.created", payload={"business_id": "x", "snapshot": None})
    )


async def test_to_doc_strips_leaked_pii_field(meili: None) -> None:
    """Search-side allowlist: even if a future producer leaks a field (e.g.
    "phone") into a snapshot, _to_doc must never let it reach the index."""
    leaked = {**BIZ_SNAP, "phone": "+919876543210"}
    doc = indexing._to_doc(leaked)
    assert "phone" not in doc
    assert doc["id"] == "business_cafe0001"


async def test_worker_process_once_indexes_published_event(bus_redis: Redis, meili: None) -> None:
    """NN#1 proof at the bus level: publish a real event on the "directory"
    stream, run process_once through a real EventConsumer, assert the
    document lands in Meilisearch. No DB session anywhere."""
    await indexing.ensure_indexes()
    consumers = [
        EventConsumer(stream, group=GROUP, name="search-worker-test") for stream in STREAMS
    ]
    for consumer in consumers:
        await consumer.ensure_group()

    await publish(
        "directory",
        "business.created",
        {"business_id": "x", "doc_id": "business_cafe0001", "snapshot": BIZ_SNAP},
    )

    did_work = await process_once(consumers)

    assert did_work is True
    res = await get_meili().search(indexing.index_uid("agri"), {"q": "kovai"})
    assert any(h["id"] == "business_cafe0001" for h in res["hits"])


async def test_worker_process_once_false_when_idle(bus_redis: Redis) -> None:
    consumers = [
        EventConsumer(stream, group=GROUP, name="search-worker-test") for stream in STREAMS
    ]
    for consumer in consumers:
        await consumer.ensure_group()

    assert await process_once(consumers) is False
