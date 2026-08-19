"""Index schema + event application for per-site Meilisearch indexes.

D19 Task 2 landed the bootstrap half: index settings and `ensure_indexes()`.
This task (D19 Task 3) adds event-driven document application: `apply_event`
consumes the fat business.*/product.* events published by
modules/directory/search_sync.py (via the "directory" stream, see
modules/search/worker.py) and turns each into upsert/delete calls per site.

Payload contract (ADR-0007): every event carries `doc_id` at the top level,
snapshot or not - the indexer keys deletes on `payload["doc_id"]`, since a
null snapshot (row no longer publicly visible) carries no other identifier.
`snapshot["sites"]` lists which per-site indexes the document belongs in;
dropping a site from that list deletes the doc from that site's index only.
"""

from typing import Any

from shared.events import Event
from shared.telemetry import get_logger

from .client import get_meili

logger = get_logger(__name__)

INDEXED_EVENT_TYPES = frozenset(
    {
        "business.created",
        "business.updated",
        "product.created",
        "product.updated",
        # Phase 2: agri-colleges. Without these two, education events land on
        # a stream this worker now reads and are then dropped here -- the
        # producer succeeds either way, so nothing would have failed.
        "institution.created",
        "institution.updated",
    }
)

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


def _to_doc(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Search-side PII allowlist: even if a future producer leaks a field
    (e.g. "phone") into a snapshot, it never reaches the index. Postgres
    (via search_sync.py) is the source of truth for what's PII-free; this is
    the last line of defence, not a licence (see modules/search/CLAUDE.md)."""
    allowed = set(DISPLAYED_ATTRIBUTES) | {"covered_pincodes", "_geo", "sites"}
    return {k: v for k, v in snapshot.items() if k in allowed}


async def apply_event(event: Event) -> None:
    """Turn one business.*/product.* fat event into per-site upsert/delete
    calls. Unknown event types are ignored (other consumer groups own them).
    Malformed events (no doc_id anywhere) are dropped with a log rather than
    raised - an exception here leaves the event unacked, and an unacked
    event stalls the whole stream (known bus limitation, see
    modules/coins/worker.py's run() comment)."""
    if event.type not in INDEXED_EVENT_TYPES:
        return
    snapshot = event.payload.get("snapshot")
    doc_id = event.payload.get("doc_id")
    if doc_id is None:
        logger.warning(
            "search worker: dropping malformed event (missing doc_id)",
            extra={"extra_fields": {"event_type": event.type}},
        )
        return
    client = get_meili()
    for site in SITES:
        uid = index_uid(site)
        if snapshot is not None and site in snapshot.get("sites", []):
            task = await client.upsert_documents(uid, [_to_doc(snapshot)])
        else:
            task = await client.delete_documents(uid, [doc_id])
        await client.wait_for_task(task)
