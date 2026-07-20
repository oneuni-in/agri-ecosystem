"""D19 Task 2: thin Meilisearch client + per-site index bootstrap.

Integration tests hit the REAL Meilisearch dev instance (ADR-0007: only the
search module talks to it; state there is disposable/rebuildable) - no
mocking of the Meili HTTP API here. Tests skip cleanly when Meili is down.
"""

import pytest

from modules.search import indexing
from modules.search.client import get_meili

pytestmark = pytest.mark.asyncio


async def test_index_uid() -> None:
    assert indexing.index_uid("milk") == "search_milk"


async def test_ensure_indexes_and_settings(meili: None) -> None:
    await indexing.ensure_indexes()
    settings = await get_meili().get_settings(indexing.index_uid("milk"))
    assert set(settings["displayedAttributes"]) == set(indexing.DISPLAYED_ATTRIBUTES)
    for banned in ("phone", "whatsapp", "email", "owner_user_id"):
        for key in ("displayedAttributes", "searchableAttributes", "filterableAttributes"):
            assert banned not in settings[key]


async def test_upsert_and_search_roundtrip(meili: None) -> None:
    await indexing.ensure_indexes()
    uid = indexing.index_uid("milk")
    client = get_meili()
    task = await client.upsert_documents(
        uid,
        [
            {
                "id": "business_deadbeef",
                "kind": "business",
                "sites": ["agri", "milk"],
                "name": "Kovai Dairy",
                "slug": "kovai-dairy",
                "description": None,
                "categories": ["dairy"],
                "district": "Coimbatore",
                "state": "Tamil Nadu",
                "covered_pincodes": ["641001"],
                "verified": True,
                "_geo": {"lat": 11.0, "lng": 76.9},
            }
        ],
    )
    await client.wait_for_task(task)
    result = await client.search(uid, {"q": "kovai dary"})  # typo on purpose
    assert result["hits"] and result["hits"][0]["id"] == "business_deadbeef"
    assert "covered_pincodes" not in result["hits"][0]  # not displayed
