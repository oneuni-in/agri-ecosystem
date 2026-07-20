"""Index schema + event application for per-site Meilisearch indexes.

This task (D19 Task 2) only lands the bootstrap half: index settings and
`ensure_indexes()`. Event-driven document application (consuming
directory/leads/etc. fat events and calling upsert/delete) lands in a later
D19 task once the search module has a consumer group of its own.
"""

from typing import Any

from .client import get_meili

# Kept identical to modules/directory/search_sync.py SITES - module
# independence (import-linter) forbids importing that constant, so any
# change here must be mirrored there by hand.
SITES = ("agri", "milk")

SEARCHABLE_ATTRIBUTES = [
    "name",
    "business_name",
    "description",
    "categories",
    "vertical",
    "district",
    "state",
]
FILTERABLE_ATTRIBUTES = [
    "kind",
    "vertical",
    "categories",
    "covered_pincodes",
    "district",
    "state",
    "verified",
    "_geo",
]
SORTABLE_ATTRIBUTES = ["_geo"]
DISPLAYED_ATTRIBUTES = [
    "id",
    "kind",
    "name",
    "slug",
    "business_name",
    "business_slug",
    "description",
    "categories",
    "vertical",
    "district",
    "state",
    "verified",
    "price_display",
    "sites",
]

INDEX_SETTINGS: dict[str, Any] = {
    "searchableAttributes": SEARCHABLE_ATTRIBUTES,
    "filterableAttributes": FILTERABLE_ATTRIBUTES,
    "sortableAttributes": SORTABLE_ATTRIBUTES,
    "displayedAttributes": DISPLAYED_ATTRIBUTES,
    # default rankingRules keep relevance ahead of sort; geo sort breaks ties
}


def index_uid(site: str) -> str:
    return f"search_{site}"


async def ensure_indexes() -> None:
    for site in SITES:
        await get_meili().ensure_index(index_uid(site), INDEX_SETTINGS)
