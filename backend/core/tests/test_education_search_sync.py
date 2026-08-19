"""Only verified, active institutions become searchable documents.

The shape tests here are cheap and would all pass against a snapshot that
never reaches Meilisearch. The integration tests at the bottom are the ones
that matter: they push a real snapshot through the real indexer into the real
dev Meilisearch and search for it. Four things about this snapshot fail
silently — a missing `id`, an `id` that disagrees with the payload's
`doc_id`, a colon in the id, and `kind` carrying the academic type instead of
the document type — and none of them raise.
"""

from datetime import date

import pytest

from modules.education.models import Institution
from modules.education.search_sync import (
    DOC_KIND,
    SITES,
    STREAM,
    doc_id,
    institution_snapshot,
)
from modules.search import indexing
from modules.search.client import get_meili
from shared.events import Event


def _inst(**over: object) -> Institution:
    base: dict[str, object] = dict(
        slug="tnau-coimbatore",
        name_en="Tamil Nadu Agricultural University",
        kind="state_agri_university",
        trust="verified",
        status="active",
        country_code="IN",
        source_url="https://tnau.ac.in/",
        last_verified_at=date(2026, 8, 10),
    )
    base.update(over)
    return Institution(**base)


def test_verified_active_institution_produces_a_snapshot() -> None:
    snap = institution_snapshot(_inst(), "Tamil Nadu")
    assert snap is not None
    assert snap["name"] == "Tamil Nadu Agricultural University"
    assert snap["slug"] == "tnau-coimbatore"
    assert snap["state"] == "Tamil Nadu"
    assert snap["sites"] == ["agri"]


def test_listed_institution_produces_no_snapshot() -> None:
    # A listed row is unverified by definition; it must never surface in hub search.
    assert institution_snapshot(_inst(trust="listed"), "Tamil Nadu") is None


def test_closed_institution_produces_no_snapshot() -> None:
    assert institution_snapshot(_inst(status="closed"), "Tamil Nadu") is None


def test_merged_institution_produces_no_snapshot() -> None:
    assert institution_snapshot(_inst(status="merged"), "Tamil Nadu") is None


def test_the_snapshot_id_matches_the_payload_doc_id() -> None:
    """Upserts write under snapshot["id"]; deletes remove payload["doc_id"].
    If the two ever diverge, a delete misses and the stale document stays
    findable forever -- with nothing failing."""
    snap = institution_snapshot(_inst(), "Tamil Nadu")
    assert snap is not None
    assert snap["id"] == doc_id("tnau-coimbatore")


def test_the_doc_id_is_a_legal_meilisearch_primary_key() -> None:
    """Meilisearch primary keys allow [a-zA-Z0-9_-] only. A colon is rejected
    at write time, which is a long way from where it would be written."""
    import re

    assert re.fullmatch(r"[A-Za-z0-9_-]+", doc_id("tnau-coimbatore"))


def test_kind_is_the_document_type_not_the_academic_one() -> None:
    """Directory publishes kind="business"/"product" and the search UI reads
    it to decide what a result is. Putting "state_agri_university" there would
    make every college result untypeable."""
    snap = institution_snapshot(_inst(kind="state_agri_university"), "Tamil Nadu")
    assert snap is not None
    assert snap["kind"] == DOC_KIND == "institution"


def test_every_snapshot_key_survives_the_indexer_allowlist() -> None:
    """_to_doc drops anything outside DISPLAYED_ATTRIBUTES + a few extras, so
    a key can be published, accepted and silently discarded. `url` was in the
    first draft of this snapshot and would have vanished exactly this way."""
    snap = institution_snapshot(_inst(), "Tamil Nadu")
    assert snap is not None
    assert indexing._to_doc(snap) == snap


def test_the_indexer_actually_accepts_our_event_type() -> None:
    """Guards the gap Step 5 was added to close.

    search_sync publishes `institution.updated` onto the `education` stream.
    Both are gated in modules/search: the worker reads a fixed STREAMS tuple
    and the indexer drops any event whose type is not in INDEXED_EVENT_TYPES.
    If either forgets institutions, publishing still succeeds and nothing is
    ever indexed -- silently.

    Imports two modules, which the import-linter independence contract forbids
    for application code. Tests are not under modules/ and so are not
    contract-checked; test_search_indexing.py does the same thing for the
    directory SITES constant, and says so.
    """
    from modules.search.indexing import INDEXED_EVENT_TYPES
    from modules.search.worker import STREAMS

    assert "institution.updated" in INDEXED_EVENT_TYPES
    assert "institution.created" in INDEXED_EVENT_TYPES
    assert STREAM in STREAMS


def test_our_sites_are_a_subset_of_the_indexers() -> None:
    """SITES is hand-mirrored across three files. Education publishes to agri
    only; publishing to a site the indexer does not know would write nothing
    and raise nothing."""
    assert set(SITES) <= set(indexing.SITES)


# ── integration: the real indexer, the real Meilisearch ──────────────


async def test_a_verified_institution_is_findable_in_hub_search(meili: None) -> None:
    """The test the shape assertions above cannot be a substitute for."""
    await indexing.ensure_indexes()
    snap = institution_snapshot(_inst(), "Tamil Nadu")
    assert snap is not None

    await indexing.apply_event(
        Event(
            id="1-1",
            type="institution.updated",
            payload={"doc_id": doc_id("tnau-coimbatore"), "snapshot": snap},
        )
    )

    res = await get_meili().search(indexing.index_uid("agri"), {"q": "agricultural university"})
    hits = [h for h in res["hits"] if h["id"] == doc_id("tnau-coimbatore")]
    assert hits, "a verified institution did not reach the agri index"
    assert hits[0]["kind"] == "institution"
    assert hits[0]["slug"] == "tnau-coimbatore"


async def test_demoting_to_listed_removes_the_document(meili: None) -> None:
    """The null-snapshot delete path (ADR-0007). A college that loses its
    verified status must stop being findable, not go stale."""
    await indexing.ensure_indexes()
    await indexing.apply_event(
        Event(
            id="1-1",
            type="institution.updated",
            payload={
                "doc_id": doc_id("tnau-coimbatore"),
                "snapshot": institution_snapshot(_inst(), "Tamil Nadu"),
            },
        )
    )
    await indexing.apply_event(
        Event(
            id="1-2",
            type="institution.updated",
            payload={
                "doc_id": doc_id("tnau-coimbatore"),
                "snapshot": institution_snapshot(_inst(trust="listed"), "Tamil Nadu"),
            },
        )
    )

    res = await get_meili().search(indexing.index_uid("agri"), {"q": "agricultural university"})
    assert not [h for h in res["hits"] if h["id"] == doc_id("tnau-coimbatore")]


async def test_institutions_never_reach_the_milk_index(meili: None) -> None:
    """sites=["agri"] is the whole gate. A college in milk.in's search would
    be a cross-site leak, not a ranking problem."""
    await indexing.ensure_indexes()
    await indexing.apply_event(
        Event(
            id="1-1",
            type="institution.updated",
            payload={
                "doc_id": doc_id("tnau-coimbatore"),
                "snapshot": institution_snapshot(_inst(), "Tamil Nadu"),
            },
        )
    )

    res = await get_meili().search(indexing.index_uid("milk"), {"q": "agricultural university"})
    assert not [h for h in res["hits"] if h["id"] == doc_id("tnau-coimbatore")]


# ── the publish wiring ───────────────────────────────────────────────


async def test_publish_emits_one_event_per_institution_including_nulls(
    monkeypatch: "pytest.MonkeyPatch",
) -> None:
    """Every institution is announced, not just the searchable ones.

    An unverified row publishes a null snapshot, which the indexer turns into
    a delete (ADR-0007). Skipping them would be the bug that leaves a college
    demoted to `listed` in a data PR still findable in hub search.
    """
    from typing import Any

    import modules.education.search_sync as search_sync

    events: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_publish(stream: str, event_type: str, payload: dict[str, Any]) -> str:
        events.append((stream, event_type, payload))
        return "1-1"

    monkeypatch.setattr(search_sync, "publish", fake_publish)

    count = await search_sync.publish_institutions(
        [(_inst(), "Tamil Nadu"), (_inst(slug="bulk-row", trust="listed"), "Kerala")]
    )

    assert count == 2
    assert [e[0] for e in events] == ["education", "education"]
    assert [e[1] for e in events] == ["institution.updated", "institution.updated"]
    assert events[0][2]["snapshot"] is not None
    assert events[1][2]["snapshot"] is None
    # The delete still needs a doc_id -- a null snapshot with no doc_id is
    # dropped by the indexer as malformed and the stale document survives.
    assert events[1][2]["doc_id"] == doc_id("bulk-row")


def test_the_cli_publishes_after_the_commit_not_before() -> None:
    """Publishing first would announce rows a rollback then removes.

    Asserted on the source because the ordering is the property, and a
    behavioural test would have to commit 772 institutions into the shared
    test database to observe it.
    """
    import inspect

    from scripts import import_education_seed

    body = inspect.getsource(import_education_seed._main)
    commit_at = body.index("await session.commit()")
    publish_at = body.index("await _publish_snapshots(session)")
    assert commit_at < publish_at
    # And nothing is published on the dry-run path at all.
    dry_run_at = body.index("DRY RUN")
    assert body.count("_publish_snapshots") == 1
    assert dry_run_at < commit_at
