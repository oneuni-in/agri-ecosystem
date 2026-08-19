"""Publish institution snapshots for the D19 search worker.

SITES is duplicated from modules/directory/search_sync.py by hand. The
import-linter contract "Modules must not import each other" forbids importing
it, so a change there must be mirrored here — the same trade directory and
search already live with.

A snapshot of None means "not publicly visible". The indexer keys deletes on
it (ADR-0007), so flipping an institution to listed, closed or merged removes
it from the index on the next import instead of leaving a stale document.

FOUR THINGS THE SNAPSHOT SHAPE HAS TO GET RIGHT, none of which fail loudly:

1. The key is `id`, not `doc_id`. Meilisearch's primary key is `"id"`
   (client.py creates every index with `primaryKey: "id"`), and `_to_doc`
   strips anything outside its allowlist. A snapshot without `id` produces a
   document with no primary key.

2. `id` must equal the event payload's `doc_id`. Upserts write under
   `snapshot["id"]`; deletes remove `payload["doc_id"]`. If the two ever
   differ, a delete silently misses and the stale document stays findable
   forever.

3. The id charset is `[a-zA-Z0-9_-]` only. Meilisearch rejects a colon, so
   this is `institution_{slug}`, matching directory's `business_{hex}` and
   `product_{hex}` — not `institution:{slug}`.

4. `kind` is the DOCUMENT type, not the academic one. Directory publishes
   `kind: "business"` / `"product"`, and the search UI reads it to decide what
   a result is and where it links. Putting `state_agri_university` there would
   make college results untypeable. The academic kind is deliberately absent:
   a hub search card needs the name, the state and a link, and adding a field
   later is additive while shipping the wrong meaning of an existing one is
   not.

There is no `url` key for the same reason directory has none — `_to_doc` would
strip it, and the UI builds the href from `kind` + `slug`.
"""

from __future__ import annotations

from typing import Any

from shared.events import publish

from .models import Institution

STREAM = "education"
SITES = ("agri",)

# The document type, mirroring directory's "business" / "product".
DOC_KIND = "institution"


def doc_id(slug: str) -> str:
    """The Meilisearch primary key for an institution.

    One function so the snapshot and the event payload cannot disagree — see
    point 2 in the module docstring.
    """
    return f"institution_{slug}"


def institution_snapshot(inst: Institution, state_name: str | None) -> dict[str, Any] | None:
    """None unless the institution is verified AND active.

    A `listed` row is unverified by definition and must never be findable in
    hub search; `closed` and `merged` rows must not be either. All three
    publish a null snapshot, which the indexer turns into a delete.
    """
    if inst.trust != "verified" or inst.status != "active":
        return None
    return {
        "id": doc_id(inst.slug),
        "kind": DOC_KIND,
        "sites": list(SITES),
        "name": inst.name_en,
        "slug": inst.slug,
        "state": state_name,
        # True by construction: a row that is not verified never gets here.
        "verified": True,
    }


async def publish_institutions(rows: list[tuple[Institution, str | None]]) -> int:
    for inst, state_name in rows:
        await publish(
            STREAM,
            "institution.updated",
            {
                "doc_id": doc_id(inst.slug),
                "snapshot": institution_snapshot(inst, state_name),
            },
        )
    return len(rows)
