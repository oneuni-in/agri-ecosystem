# D19 — Search (Meilisearch) + Location Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Typo-tolerant unified search over directory businesses + catalog products with event-driven Meilisearch indexing, plus a global location context (profile → GPS → pincode → IP) with one header LocationPill switcher and a search UI shell on web-milk.

**Architecture:** Directory publishes fat domain events (`business.created/updated`, `product.created/updated` on stream `directory`) whose payload carries a complete, PII-free search snapshot (or `null` = remove); a standalone `modules/search` worker consumes them and upserts/deletes per-site Meilisearch indexes — search never reads directory tables (module CLAUDE.md rule + ADR-0007/0008). Location context lives in `modules/identity` (profile is the persistence, per D11), with GPS reverse-geocode via `shared/geo` and a pluggable IP→state provider. Frontend: dumb `LocationPill` (exists) + new `LiveLocationPill` client wrapper mounted as an AuthCluster **sibling** in the header slots (D13/D14 lesson), location persisted in an `agri_loc` cookie (guests) and on the profile via the existing `PATCH /identity/profile` (authed).

**Tech Stack:** FastAPI + SQLAlchemy async (backend/core), Meilisearch v1.13 (already in compose), httpx (already a dep) for the Meili client — no new search SDK; `maxminddb` (new, tiny) for optional GeoIP; Next 15 apps + packages/ui (Tailwind 3, tokens only).

## Global Constraints

- NEVER commit to `main` or `dev`. Branch: `feat/d19-search-location` off `dev`. Conventional commits. PR targets `dev`. PR title: `feat(d19): search + location`.
- All backend commands run from `backend/core` (cwd). Gate before EVERY commit: `ruff format .` then `ruff check .`, `mypy .`, `lint-imports`, targeted `pytest -q -m "not slow"`. (D16 lesson: format check per task, not at the end.)
- Full local gate before first push: `mypy .` + `lint-imports` + `pytest -q -m "not slow"` (storm suite runs separately: `pytest -q -m slow`). NEVER run the slow storm inline with the main suite (D17 suite-poisoning trap).
- `git status` must show ZERO files in `AM` state before every commit.
- Import roots are `modules` and `shared`; module↔module imports are FORBIDDEN (import-linter). `modules/search` must not import `modules/directory` or read its tables. `shared` must not import `modules`.
- New routes on `SecureRouter`; `public=True` routes must be added to `backend/core/public_routes.txt` in the same commit (CI `public-routes` job diffs it).
- No offset pagination: `tests/lint_checks.py::check_offset_ban` bans `.offset(` and the uppercase word `OFFSET` in backend source. Meilisearch's JSON key `"offset"` (lowercase, not a method call) does not trip it — keep it that way (never name a helper `.offset(`).
- No PII in any index or event snapshot: no `phone`, `whatsapp`, `email`, `owner_user_id` — asserted by tests in Tasks 1 and 3.
- Publish AFTER commit, best-effort (try/except), payload captured BEFORE commit (expired-ORM-attrs trap). Copy the `_publish_best_effort` idiom from `modules/directory/admin_router.py`.
- Frontend: tokens only, no raw hex (`scripts/check-hex.mjs` gates `apps/` + `packages/ui`). Node 24 / pnpm 11 / Tailwind 3.4 (toolchain overrides the spec).
- Do not restructure `AuthCluster` internals; header widgets are siblings in `HeaderStack` slots (doc-comment contract in `packages/auth-client/src/react.tsx:76-88`). Keep e2e locators alive: `/^login$/i` button and `🪙` pill (`e2e/sso.spec.ts`).
- `python` on this host is 3.12 at `backend/core/.venv`; docker runs 3.13. No `uv`, no `gh` CLI — PR via `git credential fill` token + GitHub REST API, token exported for child processes.
- Local infra: `docker compose -f docker-compose.dev.yml up -d` (project `agri-dev`). If host port 55432 is winnat-blocked, standalone Postgres on 45432 — override BOTH `DATABASE_URL` (app_rt) and `DATABASE_ADMIN_URL` (app).
- No new DB tables in this spec → no migration, no app_rt grant changes. (Location persists on existing `identity.profiles`; Meili state is disposable per ADR-0007.)

## Shared Contracts (defined here, used across tasks)

**Event contract (stream `directory`):**

| event type | emitted from | payload |
|---|---|---|
| `business.created` | create business route | `{"business_id": str(uuid), "doc_id": "business_<uuid.hex>", "snapshot": <business snapshot> \| null}` |
| `business.updated` | update/rename/branch/coverage/categories routes; claim-approve; verification approve/reject | same shape |
| `product.created` | create product route | `{"product_id": str(uuid), "business_id": str(uuid), "doc_id": "product_<uuid.hex>", "snapshot": <product snapshot> \| null}` |
| `product.updated` | update product; product moderation approve/reject | same shape |

`doc_id` is ALWAYS present at the top level (it is the Meili document id — deletes key on it when `snapshot` is null). `snapshot: null` means "not publicly visible — remove from every index". Existing events (`business.claimed`, `directory.verification_*`, `review.approved`, `lead.*`) are untouched; notify keeps consuming them.

**Snapshot shapes (built ONLY by `modules/directory/search_sync.py`):**

```python
# business snapshot (all keys always present)
{
    "id": f"business_{business.id.hex}",   # Meili doc ids allow only [a-zA-Z0-9_-]
    "kind": "business",
    "sites": ["agri", "milk"],             # "agri" always; "milk" if dairy category or a visible milk product
    "name": str,
    "slug": str,
    "description": dict | None,            # Translated JSONB as-is ({"en": ..., "ta": ...})
    "categories": list[str],               # category slugs
    "district": str | None,                # derived from primary_pincode via geo tables
    "state": str | None,
    "covered_pincodes": list[str],         # from business_coverage
    "verified": bool,                      # verification_status == "verified"
    "_geo": {"lat": float, "lng": float} | None,  # first geocoded branch, else primary_pincode centroid
}
# product snapshot
{
    "id": f"product_{product.id.hex}",
    "kind": "product",
    "sites": ["agri", <vertical if in SITES>],
    "name": str,
    "slug": str,
    "business_name": str,
    "business_slug": str,
    "vertical": str,
    "price_display": str | None,
    "categories": list[str],               # owning business's categories
    "district": str | None, "state": str | None,
    "covered_pincodes": list[str],         # inherited from business
    "verified": bool,                      # business verification
    "_geo": {...} | None,                  # business anchor
}
```

Forbidden keys anywhere in a snapshot (recursive): `phone`, `whatsapp`, `email`, `owner_user_id`, `phone_last4`.

**Visibility rules (mirror the public read APIs):**
- business visible ⇔ `status == "active" AND deleted_at IS NULL`
- product visible ⇔ `moderation_status == "approved" AND status == "active" AND deleted_at IS NULL AND its business is visible`

**Search module public surface:**
- `modules/search/client.py`: `get_meili() -> MeiliClient`, `reset_meili() -> None`
- `modules/search/indexing.py`: `SITES = ("agri", "milk")`, `index_uid(site) -> str` (returns `f"search_{site}"`), `INDEX_SETTINGS: dict`, `async ensure_indexes() -> None`, `async apply_event(event: Event) -> None`
- `modules/search/service.py`: `async run_search(session, *, site, q, pincode=None, kind=None, vertical=None, covered=False, cursor=None, limit=20) -> SearchPage`
- `modules/search/worker.py`: `python -m modules.search.worker`, group `"search"`, streams `("directory",)`
- Route: `GET /search` (public, rate-limited)

**Location surface:**
- `shared/geo/service.py` gains `async nearest_pincode(session, lat: float, lon: float) -> Pincode | None`
- `shared/geoip.py` (new): `state_for_ip(ip: str) -> str | None`, `reset_geoip() -> None`; settings `geoip_mmdb_path: str = ""`, `trust_forwarded_for: bool = False`
- `GET /identity/location` (public + optional_auth): query `lat`, `lng`, `pincode`; returns `{"pincode": str|None, "district": str|None, "state": str|None, "source": "profile"|"gps"|"pincode"|"ip"|"none"}`. Resolution order: profile (authed, complete) → GPS → pincode → IP → none.
- Authed location WRITE = existing `PATCH /identity/profile {"pincode": ...}` (no new write endpoint; reuses `apply_location` + score recompute + `profile.completed` emit).
- Frontend cookie: name `agri_loc`, value = URL-encoded JSON `{"p": pincode, "d": district, "s": state, "src": source}`, `SameSite=Lax`, path `/`, max-age 1 year, NOT httpOnly (client-managed; SSR reads it). Never token-shaped (e2e storage scan).

---

### Task 1: Directory search snapshots + event publishes

**Files:**
- Create: `backend/core/modules/directory/search_sync.py`
- Create: `backend/core/tests/test_directory_search_sync.py`
- Modify: `backend/core/modules/directory/router.py` (create/update/rename/branch/coverage/categories routes)
- Modify: `backend/core/modules/directory/admin_router.py` (claim approve, verification approve/reject)
- Modify: `backend/core/modules/directory/catalog_router.py` (create/update product)
- Modify: `backend/core/modules/directory/catalog_admin_router.py` (product moderation)

**Interfaces:**
- Consumes: existing `modules/directory` models + `shared.events.publish`, `shared/geo` models.
- Produces: `business_snapshot(session, business_id) -> dict | None`, `product_snapshot(session, product_id) -> dict | None`, `business_event_payload(session, business_id) -> dict`, `product_event_payload(session, product_id) -> dict` — and the four events per the Shared Contracts table. Tasks 3–5 depend on these exact payloads.

- [ ] **Step 0: Branch setup**

```bash
git checkout dev && git pull && git checkout -b feat/d19-search-location
```

- [ ] **Step 1: Write failing tests for the snapshot builders**

`backend/core/tests/test_directory_search_sync.py` — use the existing `db_session` + `tn_geo_sample` fixtures (see `tests/conftest.py`); create rows via `modules.directory.service.create_business` / `catalog_service.create_product` the way `tests` for those modules already do (copy the setup helpers from the existing directory test file rather than inventing new ones).

```python
import uuid
import pytest
from modules.directory import search_sync, service
from modules.directory import catalog_service

FORBIDDEN_KEYS = {"phone", "whatsapp", "email", "owner_user_id", "phone_last4"}

def _assert_no_pii(obj: object) -> None:
    if isinstance(obj, dict):
        assert not (set(obj) & FORBIDDEN_KEYS), f"PII key leaked: {set(obj) & FORBIDDEN_KEYS}"
        for v in obj.values():
            _assert_no_pii(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_no_pii(v)

@pytest.mark.anyio
async def test_business_snapshot_visible(db_session, tn_geo_sample):
    biz = await service.create_business(
        db_session, owner_user_id=uuid.uuid4(), name="Kovai Dairy",
        type_="vendor", primary_pincode="641001",
    )
    await service.set_coverage(db_session, owner_user_id=biz.owner_user_id,
                               business_id=biz.id, pincodes=["641001", "641002"])
    snap = await search_sync.business_snapshot(db_session, biz.id)
    assert snap is not None
    assert snap["id"] == f"business_{biz.id.hex}"
    assert snap["kind"] == "business"
    assert "agri" in snap["sites"]
    assert snap["name"] == "Kovai Dairy"
    assert snap["district"] == "Coimbatore"
    assert set(snap["covered_pincodes"]) == {"641001", "641002"}
    assert snap["verified"] is False
    _assert_no_pii(snap)

@pytest.mark.anyio
async def test_business_snapshot_none_when_soft_deleted(db_session, tn_geo_sample):
    biz = await service.create_business(db_session, owner_user_id=uuid.uuid4(),
                                        name="Gone", type_="vendor", primary_pincode="641001")
    from datetime import UTC, datetime
    biz.deleted_at = datetime.now(UTC)
    await db_session.flush()
    assert await search_sync.business_snapshot(db_session, biz.id) is None

@pytest.mark.anyio
async def test_product_snapshot_requires_approved(db_session, tn_geo_sample, milk_vertical_seeded):
    # milk_vertical_seeded: reuse/copy the fixture the catalog tests use to seed
    # the "milk" vertical + spec schema (see tests for catalog_service).
    owner = uuid.uuid4()
    biz = await service.create_business(db_session, owner_user_id=owner, name="Kovai Dairy",
                                        type_="vendor", primary_pincode="641001")
    prod = await catalog_service.create_product(
        db_session, owner_user_id=owner, business_id=biz.id,
        vertical_slug="milk", name="A2 Milk 500ml", specs={...},  # copy valid specs from catalog tests
    )
    assert await search_sync.product_snapshot(db_session, prod.id) is None  # pending
    await catalog_service.moderate_product(db_session, product_id=prod.id, approve=True)
    snap = await search_sync.product_snapshot(db_session, prod.id)
    assert snap is not None
    assert snap["sites"] == ["agri", "milk"]
    assert snap["business_slug"] == biz.slug
    _assert_no_pii(snap)

@pytest.mark.anyio
async def test_business_in_milk_site_when_dairy_category(db_session, tn_geo_sample):
    ...  # create business, assign the seeded "dairy" category, assert "milk" in sites
```

(Write the remaining cases now, not later: suspended business → `None`; business with a geocoded branch → `_geo` from branch; business with no geo match → `_geo` is None and district/state None; unknown pincode tolerated.)

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_directory_search_sync.py -q` → FAIL (`No module named ... search_sync`).

- [ ] **Step 3: Implement `search_sync.py`**

```python
"""Search snapshots: the ONLY builder of index-worthy event payloads (ADR-0007).

Directory owns what is publicly indexable; modules/search owns the index.
Snapshots must never contain PII (phone/whatsapp/email/owner ids) - the
search module indexes payloads verbatim minus its own allowlist.
"""
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.geo.models import District, Pincode, State

from .catalog_models import Product, Vertical
from .models import Branch, Business, BusinessCategory, BusinessCoverage, Category

SITES = ("agri", "milk")
# Category slugs that pull a business into a vertical site even before it has products.
CATEGORY_SITES: dict[str, str] = {"dairy": "milk"}


async def _geo_context(session: AsyncSession, pincode: str) -> tuple[str | None, str | None, dict[str, float] | None]:
    row = (
        await session.execute(
            select(District.name, State.name, Pincode.centroid_lat, Pincode.centroid_lon)
            .join(District, Pincode.district_id == District.id)
            .join(State, District.state_id == State.id)
            .where(Pincode.pincode == pincode)
        )
    ).first()
    if row is None:
        return None, None, None
    district, state, lat, lon = row
    return district, state, {"lat": float(lat), "lng": float(lon)}


async def business_snapshot(session: AsyncSession, business_id: uuid.UUID) -> dict[str, Any] | None:
    biz = await session.get(Business, business_id)
    if biz is None or biz.deleted_at is not None or biz.status != "active":
        return None
    district, state, centroid = await _geo_context(session, biz.primary_pincode)
    branch_geo = (
        await session.execute(
            select(Branch.lat, Branch.lng)
            .where(Branch.business_id == business_id, Branch.deleted_at.is_(None),
                   Branch.lat.is_not(None), Branch.lng.is_not(None))
            .order_by(Branch.id)
            .limit(1)
        )
    ).first()
    geo = {"lat": float(branch_geo[0]), "lng": float(branch_geo[1])} if branch_geo else centroid
    categories = list(
        (
            await session.execute(
                select(Category.slug)
                .join(BusinessCategory, BusinessCategory.category_id == Category.id)
                .where(BusinessCategory.business_id == business_id)
            )
        ).scalars()
    )
    covered = list(
        (
            await session.execute(
                select(BusinessCoverage.pincode).where(BusinessCoverage.business_id == business_id)
            )
        ).scalars()
    )
    sites = ["agri"]
    for slug in categories:
        site = CATEGORY_SITES.get(slug)
        if site and site not in sites:
            sites.append(site)
    product_verticals = (
        await session.execute(
            select(Product.vertical_slug)
            .where(Product.business_id == business_id, Product.deleted_at.is_(None),
                   Product.status == "active", Product.moderation_status == "approved")
            .distinct()
        )
    ).scalars()
    for vertical in product_verticals:
        if vertical in SITES and vertical not in sites:
            sites.append(vertical)
    return {
        "id": f"business_{biz.id.hex}",
        "kind": "business",
        "sites": sites,
        "name": biz.name,
        "slug": biz.slug,
        "description": biz.description,
        "categories": categories,
        "district": district,
        "state": state,
        "covered_pincodes": covered,
        "verified": biz.verification_status == "verified",
        "_geo": geo,
    }


async def product_snapshot(session: AsyncSession, product_id: uuid.UUID) -> dict[str, Any] | None:
    prod = await session.get(Product, product_id)
    if (
        prod is None or prod.deleted_at is not None
        or prod.status != "active" or prod.moderation_status != "approved"
    ):
        return None
    parent = await business_snapshot(session, prod.business_id)
    if parent is None:
        return None
    sites = ["agri"]
    if prod.vertical_slug in SITES:
        sites.append(prod.vertical_slug)
    return {
        "id": f"product_{prod.id.hex}",
        "kind": "product",
        "sites": sites,
        "name": prod.name,
        "slug": prod.slug,
        "business_name": parent["name"],
        "business_slug": parent["slug"],
        "vertical": prod.vertical_slug,
        "price_display": prod.price_display,
        "categories": parent["categories"],
        "district": parent["district"],
        "state": parent["state"],
        "covered_pincodes": parent["covered_pincodes"],
        "verified": parent["verified"],
        "_geo": parent["_geo"],
    }


async def business_event_payload(session: AsyncSession, business_id: uuid.UUID) -> dict[str, Any]:
    return {"business_id": str(business_id),
            "snapshot": await business_snapshot(session, business_id)}


async def product_event_payload(session: AsyncSession, product_id: uuid.UUID) -> dict[str, Any]:
    snap = await product_snapshot(session, product_id)
    prod = await session.get(Product, product_id)
    assert prod is not None
    return {"product_id": str(product_id), "business_id": str(prod.business_id),
            "snapshot": snap}
```

Adjust column/enum names against `models.py`/`catalog_models.py` while implementing — the enums may compare as strings or enum members; match how `covers.py`/`catalog_service.py` compare them.

- [ ] **Step 4: Run snapshot tests** — `pytest tests/test_directory_search_sync.py -q` → PASS.

- [ ] **Step 5: Write failing publish-wiring tests**

Append to the same test file. Pattern: monkeypatch `publish` in each ROUTER module (they import it by name) with a recorder, drive the route via the app test client the way existing directory router tests do, assert `(stream, event_type)` and that `payload["snapshot"]` is a dict/None:

```python
@pytest.mark.anyio
async def test_create_business_publishes_created(client_owner, captured_events):
    resp = await client_owner.post("/directory/businesses", json={...})
    assert resp.status_code == 201
    types = [e[1] for e in captured_events]
    assert "business.created" in types
```

Cover: create business → `business.created`; PATCH business, rename, add branch, PUT coverage, PUT categories → `business.updated`; claim approve → `business.updated` (in addition to the existing `business.claimed` — assert BOTH); verification approve → `business.updated`; create product → `product.created`; PATCH product + moderation approve → `product.updated`. `captured_events` is a small fixture monkeypatching `shared.events.publish` **at each router module's imported name** (e.g. `monkeypatch.setattr(router_module, "publish", recorder)`).

- [ ] **Step 6: Run to verify failure** — new tests FAIL (no events captured).

- [ ] **Step 7: Wire the publishes**

In each route (after the service call, BEFORE `session.commit()`): `payload = await search_sync.business_event_payload(session, biz.id)` — then AFTER commit: `await _publish_best_effort("business.updated", payload)` (each directory router already has, or gets, the local `_publish_best_effort(event_type, payload)` helper wrapping `publish(EVENT_STREAM, ...)` in try/except; `EVENT_STREAM = "directory"`). For routes that don't currently commit-then-publish, follow the exact choreography in `admin_router.py` (capture → commit → best-effort publish).

- [ ] **Step 8: Run tests** — `pytest tests/test_directory_search_sync.py -q` → PASS. Then the module gate: `ruff format . && ruff check . && mypy . && lint-imports && pytest -q -m "not slow" tests/test_directory_search_sync.py`.

- [ ] **Step 9: Commit**

```bash
git add backend/core/modules/directory backend/core/tests/test_directory_search_sync.py
git commit -m "feat(d19): directory publishes search snapshots on business/product change"
```

---

### Task 2: Meilisearch client + per-site index bootstrap

**Files:**
- Create: `backend/core/modules/search/client.py`
- Create: `backend/core/modules/search/indexing.py` (settings + `ensure_indexes` only in this task)
- Create: `backend/core/tests/test_search_client.py`
- Modify: `backend/core/tests/conftest.py` (add `reset_meili()` to `_reset_state`; add a `meili` fixture that skips when unreachable)

**Interfaces:**
- Consumes: `settings.meilisearch_url`, `settings.meilisearch_master_key` (already exist), httpx.
- Produces: `MeiliClient` with `async ensure_index(uid, settings_body)`, `async upsert_documents(uid, docs)`, `async delete_documents(uid, ids)`, `async search(uid, body) -> dict`, `async wait_for_task(task_uid)`, `async get_settings(uid) -> dict`, `async delete_index(uid)`, `async health() -> bool`; module-level `get_meili()` / `reset_meili()` singleton; `INDEX_SETTINGS`, `index_uid(site)`, `ensure_indexes()`.

- [ ] **Step 1: Failing tests**

```python
# backend/core/tests/test_search_client.py
import pytest
from modules.search import indexing
from modules.search.client import get_meili

pytestmark = pytest.mark.anyio

async def test_index_uid():
    assert indexing.index_uid("milk") == "search_milk"

async def test_ensure_indexes_and_settings(meili):
    await indexing.ensure_indexes()
    settings = await get_meili().get_settings(indexing.index_uid("milk"))
    assert set(settings["displayedAttributes"]) == set(indexing.DISPLAYED_ATTRIBUTES)
    for banned in ("phone", "whatsapp", "email", "owner_user_id"):
        for key in ("displayedAttributes", "searchableAttributes", "filterableAttributes"):
            assert banned not in settings[key]

async def test_upsert_and_search_roundtrip(meili):
    await indexing.ensure_indexes()
    uid = indexing.index_uid("milk")
    client = get_meili()
    task = await client.upsert_documents(uid, [{
        "id": "business_deadbeef", "kind": "business", "sites": ["agri", "milk"],
        "name": "Kovai Dairy", "slug": "kovai-dairy", "description": None,
        "categories": ["dairy"], "district": "Coimbatore", "state": "Tamil Nadu",
        "covered_pincodes": ["641001"], "verified": True,
        "_geo": {"lat": 11.0, "lng": 76.9},
    }])
    await client.wait_for_task(task)
    result = await client.search(uid, {"q": "kovai dary"})  # typo on purpose
    assert result["hits"] and result["hits"][0]["id"] == "business_deadbeef"
    assert "covered_pincodes" not in result["hits"][0]  # not displayed
```

`meili` fixture in conftest: async fixture that calls `get_meili().health()`; `pytest.skip("meilisearch unreachable")` on failure; deletes the `search_*` test indexes before yield (namespacing: in tests override `index_uid` prefix? No — simpler: fixture deletes indexes `search_agri`/`search_milk` before AND after, dev Meili is disposable state per ADR-0007). Register `reset_meili` in `_reset_state` alongside `reset_redis()` etc. (D01-B test-state hygiene rule).

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_search_client.py -q` → FAIL (import error).

- [ ] **Step 3: Implement `client.py`**

```python
"""Thin async Meilisearch v1.13 HTTP client (httpx). Only this module talks to Meili."""
import asyncio
from typing import Any

import httpx

from settings import get_settings

_client: "MeiliClient | None" = None


class MeiliError(RuntimeError):
    pass


class MeiliClient:
    def __init__(self, base_url: str, master_key: str) -> None:
        headers = {"Authorization": f"Bearer {master_key}"} if master_key else {}
        self._http = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10.0)

    async def _request(self, method: str, path: str, json_body: Any | None = None) -> Any:
        resp = await self._http.request(method, path, json=json_body)
        if resp.status_code >= 400:
            raise MeiliError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else None

    async def health(self) -> bool:
        try:
            await self._request("GET", "/health")
            return True
        except (MeiliError, httpx.HTTPError):
            return False

    async def ensure_index(self, uid: str, settings_body: dict[str, Any]) -> None:
        try:
            await self._request("POST", "/indexes", {"uid": uid, "primaryKey": "id"})
        except MeiliError as exc:
            if "index_already_exists" not in str(exc):
                raise
        task = await self._request("PATCH", f"/indexes/{uid}/settings", settings_body)
        await self.wait_for_task(task["taskUid"])

    async def upsert_documents(self, uid: str, docs: list[dict[str, Any]]) -> int:
        task = await self._request("PUT", f"/indexes/{uid}/documents", docs)
        return int(task["taskUid"])

    async def delete_documents(self, uid: str, ids: list[str]) -> int:
        task = await self._request("POST", f"/indexes/{uid}/documents/delete-batch", ids)
        return int(task["taskUid"])

    async def search(self, uid: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/indexes/{uid}/search", body)  # type: ignore[no-any-return]

    async def get_settings(self, uid: str) -> dict[str, Any]:
        return await self._request("GET", f"/indexes/{uid}/settings")  # type: ignore[no-any-return]

    async def delete_index(self, uid: str) -> None:
        try:
            await self._request("DELETE", f"/indexes/{uid}")
        except MeiliError as exc:
            if "index_not_found" not in str(exc):
                raise

    async def wait_for_task(self, task_uid: int, timeout: float = 10.0) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            task = await self._request("GET", f"/tasks/{task_uid}")
            if task["status"] == "succeeded":
                return
            if task["status"] in ("failed", "canceled"):
                raise MeiliError(f"task {task_uid} {task['status']}: {task.get('error')}")
            if asyncio.get_event_loop().time() > deadline:
                raise MeiliError(f"task {task_uid} timed out")
            await asyncio.sleep(0.05)

    async def aclose(self) -> None:
        await self._http.aclose()


def get_meili() -> MeiliClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = MeiliClient(s.meilisearch_url, s.meilisearch_master_key)
    return _client


def reset_meili() -> None:
    global _client
    _client = None  # old httpx client GC'd; fine for tests
```

- [ ] **Step 4: Implement index settings in `indexing.py` (bootstrap part)**

```python
"""Index schema + event application for per-site Meilisearch indexes."""
from typing import Any

from shared.events import Event

from .client import get_meili

SITES = ("agri", "milk")

SEARCHABLE_ATTRIBUTES = ["name", "business_name", "description", "categories",
                         "vertical", "district", "state"]
FILTERABLE_ATTRIBUTES = ["kind", "vertical", "categories", "covered_pincodes",
                         "district", "state", "verified", "_geo"]
SORTABLE_ATTRIBUTES = ["_geo"]
DISPLAYED_ATTRIBUTES = ["id", "kind", "name", "slug", "business_name", "business_slug",
                        "description", "categories", "vertical", "district", "state",
                        "verified", "price_display", "sites"]

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
```

- [ ] **Step 5: Run tests** — `pytest tests/test_search_client.py -q` with the compose stack up → PASS (skips cleanly when Meili down). Gate: `ruff format . && ruff check . && mypy . && lint-imports`.

- [ ] **Step 6: Commit** — `git add backend/core/modules/search backend/core/tests/test_search_client.py backend/core/tests/conftest.py && git commit -m "feat(d19): meilisearch client + per-site index bootstrap"`

---

### Task 3: Event-driven indexer + standalone worker + compose service

**Files:**
- Modify: `backend/core/modules/search/indexing.py` (add `apply_event`)
- Create: `backend/core/modules/search/worker.py`
- Create: `backend/core/tests/test_search_indexing.py`
- Modify: `docker-compose.dev.yml` (new `search-worker` service)

**Interfaces:**
- Consumes: Task 1 event payloads, Task 2 client, `shared.events.EventConsumer`.
- Produces: `async apply_event(event: Event) -> None`; worker entrypoint `python -m modules.search.worker` with `async process_once(consumers, ...) -> bool` (returns "did work", so the loop AND tests share one code path).

- [ ] **Step 1: Failing tests**

```python
# backend/core/tests/test_search_indexing.py
import pytest
from shared.events import Event
from modules.search import indexing
from modules.search.client import get_meili

pytestmark = pytest.mark.anyio

BIZ_SNAP = {  # copy of a realistic Task-1 snapshot
    "id": "business_cafe0001", "kind": "business", "sites": ["agri", "milk"],
    "name": "Kovai Dairy", "slug": "kovai-dairy", "description": None,
    "categories": ["dairy"], "district": "Coimbatore", "state": "Tamil Nadu",
    "covered_pincodes": ["641001"], "verified": False,
    "_geo": {"lat": 11.0, "lng": 76.9},
}

async def test_upsert_on_snapshot(meili):
    await indexing.ensure_indexes()
    await indexing.apply_event(Event(id="1-1", type="business.created",
                                     payload={"business_id": "x", "snapshot": BIZ_SNAP}))
    for site in ("agri", "milk"):
        res = await get_meili().search(indexing.index_uid(site), {"q": "kovai"})
        assert any(h["id"] == "business_cafe0001" for h in res["hits"])

async def test_delete_on_null_snapshot(meili):
    await indexing.ensure_indexes()
    await indexing.apply_event(Event(id="1-1", type="business.created",
                                     payload={"business_id": "x", "snapshot": BIZ_SNAP}))
    await indexing.apply_event(Event(id="1-2", type="business.updated",
                                     payload={"business_id": "x", "snapshot": None,
                                              "doc_id": "business_cafe0001"}))
    ...  # assert gone from BOTH indexes

async def test_site_narrowing_removes_from_dropped_site(meili):
    # snapshot loses "milk" from sites -> deleted from search_milk, kept in search_agri
    ...

async def test_unknown_event_types_ignored(meili):
    await indexing.apply_event(Event(id="1-3", type="lead.created", payload={}))  # no raise
```

**Contract fix surfaced by the delete test:** a `null` snapshot carries no doc id — Task 1's payloads must include `doc_id` (`business_{hex}` / `product_{hex}`) at the TOP level of every event payload, snapshot or not. Add `"doc_id"` to `business_event_payload`/`product_event_payload` in Task 1 (one-line each) and to the Shared Contracts section semantics: indexer keys deletes on `payload["doc_id"]`.

- [ ] **Step 2: Verify failure**, then **Step 3: implement `apply_event`**

```python
INDEXED_EVENT_TYPES = frozenset({
    "business.created", "business.updated", "product.created", "product.updated",
})

async def apply_event(event: Event) -> None:
    if event.type not in INDEXED_EVENT_TYPES:
        return
    snapshot = event.payload.get("snapshot")
    doc_id = event.payload.get("doc_id")
    if doc_id is None:
        return  # malformed; DLQ via non-ack would stall the stream - drop and log instead
    client = get_meili()
    for site in SITES:
        uid = index_uid(site)
        if snapshot is not None and site in snapshot.get("sites", []):
            task = await client.upsert_documents(uid, [_to_doc(snapshot)])
        else:
            task = await client.delete_documents(uid, [doc_id])
        await client.wait_for_task(task)

def _to_doc(snapshot: dict[str, Any]) -> dict[str, Any]:
    allowed = set(DISPLAYED_ATTRIBUTES) | {"covered_pincodes", "_geo", "sites"}
    return {k: v for k, v in snapshot.items() if k in allowed}
```

(`_to_doc` is the search-side allowlist — even if a future producer leaks a field into a snapshot, it never reaches the index. Add a unit test: a snapshot with an injected `"phone"` key indexes without it.)

- [ ] **Step 4: implement `worker.py`** — clone `modules/coins/worker.py` shape exactly (see that file): `STREAMS = ("directory",)`, `GROUP = "search"`, `NAME = "search-worker-1"`, per-event `try: await apply_event(e); await consumer.ack(e) except Exception: log, no ack`; `reap_poison()` each pass; `ensure_indexes()` once at startup; factor the inner pass into `async def process_once(consumers) -> bool` used by `run()`; add a worker test that publishes a real event to the test-redis stream, builds a consumer, runs `process_once`, and asserts the doc landed (this is the NN#1 "create business → appears in index" proof at the bus level; needs both `redis` and `meili` fixtures). No DB session needed — payloads are self-contained (that's the point of fat events).

- [ ] **Step 5: compose service** — in `docker-compose.dev.yml`, add sibling of `worker`:

```yaml
  search-worker:
    build: ./backend/core
    command: ["python", "-m", "modules.search.worker"]
    environment:
      DATABASE_URL: ${DATABASE_URL}          # match the existing worker service's env block exactly
      REDIS_URL: redis://redis:6379/0
      MEILISEARCH_URL: http://meilisearch:7700
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
      meilisearch: { condition: service_healthy }
```

(Copy the existing `worker` service env block verbatim and add `MEILISEARCH_URL` + the meilisearch dependency; keep values identical to that block, not this sketch.) Verify: `docker compose -f docker-compose.dev.yml config --quiet`.

- [ ] **Step 6: Run** `pytest tests/test_search_indexing.py -q` → PASS; gate; commit `feat(d19): event-driven search indexer + worker`.

---

### Task 4: Full-reindex script

**Files:**
- Create: `backend/core/scripts/reindex_search.py`
- Create: `backend/core/tests/test_reindex_search.py`

**Interfaces:**
- Consumes: `modules.directory.search_sync` payload builders + `shared.events.publish` (scripts may import multiple modules; `modules.search` itself still never imports directory).
- Produces: `python -m scripts.reindex_search` — republishes a `business.updated`/`product.updated` event for EVERY business/product id (including invisible ones → tombstones), so the worker rebuilds indexes from Postgres truth (ADR-0007 "indexes are rebuildable").

- [ ] **Step 1: Failing test** — `test_reindex_publishes_for_all_rows`: seed 2 businesses (1 soft-deleted) + 1 product via services, monkeypatch `scripts.reindex_search.publish` with a recorder, run `await reindex_search.run(session)`, assert one event per row and that the soft-deleted one has `snapshot None`.
- [ ] **Step 2: verify FAIL** → **Step 3: implement**

```python
"""Rebuild search indexes: republish every entity's snapshot over the bus.
Run: python -m scripts.reindex_search   (worker must be running to apply)."""
import asyncio

from sqlalchemy import select

from modules.directory.models import Business
from modules.directory.catalog_models import Product
from modules.directory.search_sync import business_event_payload, product_event_payload
from shared.db import get_sessionmaker   # match the import used by scripts/ today
from shared.events import publish

STREAM = "directory"


async def run(session) -> int:
    count = 0
    for biz_id in (await session.execute(
            select(Business.id).execution_options(include_deleted=True))).scalars():
        await publish(STREAM, "business.updated", await business_event_payload(session, biz_id))
        count += 1
    for prod_id in (await session.execute(
            select(Product.id).execution_options(include_deleted=True))).scalars():
        await publish(STREAM, "product.updated", await product_event_payload(session, prod_id))
        count += 1
    return count


async def main() -> None:
    maker = get_sessionmaker()
    async with maker() as session:
        count = await run(session)
    print(f"republished {count} search events")


if __name__ == "__main__":
    asyncio.run(main())
```

(Confirm the soft-delete listener requires `include_deleted=True` for these selects the way slug-uniqueness checks do; also confirm `get_sessionmaker` import path from an existing script like `scripts/coins_referral_reset.py` and match it. `product_event_payload` must tolerate soft-deleted rows — its `session.get` + assert must not choke; adjust to return a tombstone payload when the row exists but is invisible.)

- [ ] **Step 4: PASS, gate, commit** `feat(d19): full-reindex script republishes snapshots over the bus`.

---

### Task 5: Unified search API (`GET /search`)

**Files:**
- Modify: `backend/core/modules/search/router.py` (has an empty SecureRouter already)
- Create: `backend/core/modules/search/service.py` (replacing the stub)
- Create: `backend/core/tests/test_search_api.py`
- Modify: `backend/core/public_routes.txt` (add `/search`)

**Interfaces:**
- Consumes: Task 2 client/indexing, `shared.geo.service.centroid_for_pincode`, `shared.pagination.InvalidCursorError` semantics (bespoke cursor here — Meili results aren't UUID-keyset-able; precedent: `covers.py` bespoke cursor).
- Produces: `GET /search?site=&q=&pincode=&kind=&vertical=&covered=&cursor=&limit=` → `SearchPage {items: list[SearchHit], next_cursor: str | null}`. `SearchHit` mirrors `DISPLAYED_ATTRIBUTES` (no `covered_pincodes`, no `_geo`, no PII by construction).

- [ ] **Step 1: Failing tests** — seed docs via `indexing.apply_event` (Task 3), then through the app test client:
  - `test_search_basic`: `GET /search?site=milk&q=kovai+dary` → 200, typo-tolerant hit.
  - `test_pincode_boost`: two docs equal relevance, different `_geo`; `pincode=641001` → nearer first (seed `tn_geo_sample` for the centroid).
  - `test_covered_filter`: `covered=true&pincode=641001` filters to `covered_pincodes = 641001`.
  - `test_cursor_walk`: 3 docs, `limit=2` → page 1 has `next_cursor`, page 2 returns the third, no repeats; tampered cursor → 400 `invalid_cursor`; cursor for a DIFFERENT query string → 400.
  - `test_no_pii_in_response`: `"phone"`/`"email"` not in `resp.text`.
  - `test_unknown_site_404`.
- [ ] **Step 2: verify FAIL** → **Step 3: implement**

`service.py` core:

```python
import base64
import binascii
import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.geo.service import centroid_for_pincode

from .client import get_meili
from .indexing import SITES, index_uid

MAX_DEPTH = 500  # bounded exploration; deep scraping goes through covers()/lists instead


class InvalidSearchCursor(ValueError):
    pass


def _query_hash(site: str, q: str, pincode: str | None, kind: str | None,
                vertical: str | None, covered: bool) -> str:
    raw = "|".join([site, q, pincode or "", kind or "", vertical or "", str(covered)])
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def encode_search_cursor(start: int, qhash: str) -> str:
    return base64.urlsafe_b64encode(json.dumps({"s": start, "h": qhash}).encode()).decode()


def decode_search_cursor(cursor: str, qhash: str) -> int:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        start = int(data["s"])
        if data["h"] != qhash or start < 0 or start > MAX_DEPTH:
            raise InvalidSearchCursor(cursor)
        return start
    except (ValueError, KeyError, binascii.Error) as exc:
        raise InvalidSearchCursor(cursor) from exc


async def run_search(session: AsyncSession, *, site: str, q: str,
                     pincode: str | None = None, kind: str | None = None,
                     vertical: str | None = None, covered: bool = False,
                     cursor: str | None = None, limit: int = 20) -> dict[str, Any]:
    qhash = _query_hash(site, q, pincode, kind, vertical, covered)
    start = decode_search_cursor(cursor, qhash) if cursor else 0
    filters: list[str] = []
    if kind:
        filters.append(f'kind = "{kind}"')
    if vertical:
        filters.append(f'vertical = "{vertical}"')
    if covered and pincode:
        filters.append(f'covered_pincodes = "{pincode}"')
    body: dict[str, Any] = {"q": q, "limit": limit + 1, "offset": start}
    if filters:
        body["filter"] = " AND ".join(filters)
    if pincode:
        centroid = await centroid_for_pincode(session, pincode)
        if centroid is not None:
            lat, lon = centroid
            body["sort"] = [f"_geoPoint({float(lat)}, {float(lon)}):asc"]
    result = await get_meili().search(index_uid(site), body)
    hits = result["hits"]
    has_more = len(hits) > limit
    items = hits[:limit]
    next_start = start + limit
    next_cursor = (encode_search_cursor(next_start, qhash)
                   if has_more and next_start < MAX_DEPTH else None)
    return {"items": items, "next_cursor": next_cursor}
```

`router.py`: `GET ""` on the existing `SecureRouter(prefix="/search")` with `public=True`; validate `site in SITES` else 404 `unknown_site`; `q` max length 200; `pincode` regex `^\d{6}$`; `limit` 1–50; map `InvalidSearchCursor` → 400 `invalid_cursor`; response model `SearchPage(BaseModel)` with `SearchHit(BaseModel, extra="ignore")` fields exactly = displayed attributes (all Optional except `id`, `kind`, `name`). Add `/search` to `public_routes.txt` with a one-line justification comment matching the file's format.

- [ ] **Step 4: PASS, gate** (public-routes: run `python scripts/dump_public_routes.py --check`), **commit** `feat(d19): unified public search endpoint with geo boost + cursor paging`.

---

### Task 6: Location resolution primitives (nearest pincode + GeoIP provider)

**Files:**
- Modify: `backend/core/shared/geo/service.py` (add `nearest_pincode`)
- Create: `backend/core/shared/geoip.py`
- Modify: `backend/core/settings.py` (add `geoip_mmdb_path: str = ""`, `trust_forwarded_for: bool = False`)
- Modify: `backend/core/pyproject.toml` (add `maxminddb>=2.6`)
- Create: `backend/core/tests/test_location_primitives.py`
- Modify: `backend/core/tests/conftest.py` (`reset_geoip()` in `_reset_state`)

**Interfaces:**
- Produces: `async nearest_pincode(session, lat, lon) -> Pincode | None` (None when out of range ±90/±180 or table empty); `state_for_ip(ip: str) -> str | None` (None when `geoip_mmdb_path` unset, file missing, ip unparseable, or country != India; else the subdivision name matched case-insensitively against `geo.states.name` — matching happens in the caller, this returns the raw subdivision string); `reset_geoip()`.

- [ ] **Step 1: Failing tests** — `nearest_pincode` with `tn_geo_sample`: coords near Coimbatore → `641001`; coords near Chennai → `600001`; `lat=95` → None. `state_for_ip`: path unset → None; monkeypatched fake reader object (set `shared.geoip._reader` directly) returning a maxmind-shaped dict → `"Tamil Nadu"`; reader raising → None.
- [ ] **Step 2: FAIL** → **Step 3: implement**

`nearest_pincode` (SQL over 2k rows, no PostGIS needed — same integer-metre haversine idiom as `covers.py`):

```python
async def nearest_pincode(session: AsyncSession, lat: float, lon: float) -> Pincode | None:
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    row = await session.execute(
        text("""
            SELECT id FROM geo.pincodes
            ORDER BY 2 * 6371000 * asin(sqrt(
                power(sin(radians((centroid_lat - :lat) / 2)), 2)
                + cos(radians(:lat)) * cos(radians(centroid_lat))
                * power(sin(radians((centroid_lon - :lon) / 2)), 2)))
            LIMIT 1
        """),
        {"lat": lat, "lon": lon},
    )
    pk = row.scalar()
    return await session.get(Pincode, pk) if pk else None
```

`shared/geoip.py`:

```python
"""Optional IP -> state (subdivision) lookup. State-level only, advisory only.

Provisioning the GeoLite2 mmdb is an owner/VPS action; unset path = feature off.
"""
import ipaddress
import logging
from typing import Any

from settings import get_settings

logger = logging.getLogger(__name__)
_reader: Any | None = None
_load_failed = False


def _get_reader() -> Any | None:
    global _reader, _load_failed
    if _reader is not None or _load_failed:
        return _reader
    path = get_settings().geoip_mmdb_path
    if not path:
        _load_failed = True
        return None
    try:
        import maxminddb
        _reader = maxminddb.open_database(path)
    except Exception:
        logger.warning("geoip.open_failed", extra={"extra_fields": {"path": path}})
        _load_failed = True
    return _reader


def state_for_ip(ip: str) -> str | None:
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    reader = _get_reader()
    if reader is None:
        return None
    try:
        rec = reader.get(ip)
    except Exception:
        return None
    if not isinstance(rec, dict):
        return None
    if rec.get("country", {}).get("iso_code") != "IN":
        return None
    subdivisions = rec.get("subdivisions") or []
    if not subdivisions:
        return None
    names = subdivisions[0].get("names", {})
    return names.get("en")


def reset_geoip() -> None:
    global _reader, _load_failed
    if _reader is not None:
        try:
            _reader.close()
        except Exception:
            pass
    _reader = None
    _load_failed = False
```

- [ ] **Step 4: PASS, gate, commit** `feat(d19): nearest-pincode + optional geoip primitives`.

---

### Task 7: `GET /identity/location` — resolution order endpoint

**Files:**
- Create: `backend/core/modules/identity/location_router.py`
- Modify: `backend/core/main.py` (mount `location_router` in `MODULE_ROUTERS`)
- Modify: `backend/core/public_routes.txt` (add `/identity/location`)
- Create: `backend/core/tests/test_location_context.py`

**Interfaces:**
- Consumes: `optional_auth` (`shared/security.py` — route needs `public=True` AND explicit `Depends(optional_auth)`, see `leads_router.py:85` precedent), `Profile` via `get_or_create_profile`/direct select, `district_for_pincode`, `nearest_pincode`, `state_for_ip`.
- Produces: `LocationOut(IdentityPublicSchema)`: `pincode: str | None`, `district: str | None`, `state: str | None`, `source: Literal["profile","gps","pincode","ip","none"]`. (IdentityPublicSchema bans UUID-typed fields and `user_id` — these are all plain strings, compliant by construction.)

- [ ] **Step 1: Failing tests** — one test per rung, each proving it BEATS the rungs below it (NN#2):
  - authed user with complete profile location + `?lat/lng&pincode=` also present → `source=profile`, profile's pincode wins.
  - authed user with INCOMPLETE profile location (no pincode) + gps coords → `source=gps`.
  - anonymous + valid `lat/lng` → `source=gps`, nearest pincode's district/state.
  - anonymous + `pincode=641001` only → `source=pincode`.
  - anonymous + nothing, `state_for_ip` monkeypatched → `"Tamil Nadu"` → `source=ip`, `pincode`/`district` None, `state="Tamil Nadu"`.
  - anonymous + nothing, geoip off → `source=none`, all None.
  - gps coords out of range + pincode present → falls through to `source=pincode`.
  - unknown pincode param (no geo row) + nothing else → `source=none` (unknown pincode is NOT trusted — server validates, per THREAT MODEL "location spoofing").
- [ ] **Step 2: FAIL** → **Step 3: implement**

```python
"""Global location context (D19): profile -> GPS -> pincode -> IP -> none.

Server validates every rung against geo tables; GPS/IP are advisory
(THREAT: location spoofing) - nothing here writes state. Authed writes go
through PATCH /identity/profile (pincode), the single location writer.
"""
from typing import Literal

from fastapi import Depends, Query, Request

from shared.geo.service import district_for_pincode, nearest_pincode
from shared.geoip import state_for_ip
from shared.security import SecureRouter, optional_auth
from settings import get_settings

from .schemas import IdentityPublicSchema
# import session dep, Profile, State the way profile_router.py does

location_router = SecureRouter(prefix="/identity/location", tags=["identity"])


class LocationOut(IdentityPublicSchema):
    pincode: str | None
    district: str | None
    state: str | None
    source: Literal["profile", "gps", "pincode", "ip", "none"]


def _client_ip(request: Request) -> str | None:
    if get_settings().trust_forwarded_for:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def _context_for_pincode(session, pincode: str, source: str) -> LocationOut | None:
    district = await district_for_pincode(session, pincode)
    if district is None:
        return None
    state = await session.scalar(select(State).where(State.id == district.state_id))
    return LocationOut(pincode=pincode, district=district.name,
                       state=state.name if state else None, source=source)


@location_router.get("", public=True, dependencies=[Depends(optional_auth)])
async def get_location_context(
    request: Request,
    session: SessionDep,
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
    pincode: str | None = Query(default=None, pattern=r"^\d{6}$"),
) -> LocationOut:
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        profile = await session.scalar(select(Profile).where(Profile.user_id == principal.user_id))
        if profile is not None and profile.pincode and profile.district and profile.state:
            return LocationOut(pincode=profile.pincode, district=profile.district,
                               state=profile.state, source="profile")
    if lat is not None and lng is not None:
        near = await nearest_pincode(session, lat, lng)
        if near is not None:
            out = await _context_for_pincode(session, near.pincode, "gps")
            if out is not None:
                return out
    if pincode is not None:
        out = await _context_for_pincode(session, pincode, "pincode")
        if out is not None:
            return out
    ip = _client_ip(request)
    if ip is not None:
        state_name = state_for_ip(ip)
        if state_name is not None:
            return LocationOut(pincode=None, district=None, state=state_name, source="ip")
    return LocationOut(pincode=None, district=None, state=None, source="none")
```

Mount in `main.py` next to the other identity routers; add `/identity/location` to `public_routes.txt` (justification: anonymous location context, no data written, rate-limited).

- [ ] **Step 4: PASS**, run `python scripts/dump_public_routes.py --check`, full backend gate, **commit** `feat(d19): location context endpoint with profile>gps>pincode>ip order`.

---

### Task 8: packages/ui — location cookie lib + LiveLocationPill + i18n

**Files:**
- Create: `packages/ui/src/lib/location.ts`
- Create: `packages/ui/src/lib/location.test.ts`
- Create: `packages/ui/src/components/live-location-pill.tsx`
- Modify: `packages/ui/src/index.ts` (export both)
- Modify: `packages/ui/src/i18n/messages/en.json`, `ta.json`, `hi.json` (add `ui.location.*`)

**Interfaces:**
- Consumes: existing `LocationPill`, `PincodeInput`, `GpsPill`, `Modal` (uncontrolled Radix — trigger prop), `cn`.
- Produces:
  - `location.ts`: `LOC_COOKIE = "agri_loc"`, `interface LocContext { pincode: string | null; district: string | null; state: string | null; source: "profile"|"gps"|"pincode"|"ip"|"none" }`, `parseLocCookie(cookieValue: string | undefined) -> LocContext | null`, `serializeLocCookie(loc: LocContext) -> string` (full `Set-Cookie`-ready string with `Path=/; Max-Age=31536000; SameSite=Lax`), `locLabel(loc: LocContext | null) -> string | null` (returns `"District · 641001"`, `"District"`, `"State"`, or null).
  - `LiveLocationPill({ contextEndpoint = "/api/identity/location", profileEndpoint = "/api/identity/profile", isAuthed = false, onChanged }: {...})` — client component.
- vitest is node-env with NO jsdom: test `parseLocCookie`/`serializeLocCookie`/`locLabel` logic only (mirror `coins-balance.test.ts` style). Cookie value must never be token-shaped (`eyJ...`) — plain URL-encoded JSON starting `%7B` (e2e storage-scan safe); assert that in a test.

- [ ] **Step 1: Failing logic tests** (`pnpm --filter @agri/ui test`): parse round-trip, malformed JSON → null, missing keys → null, label precedence (district+pincode → `"D · P"`; state only → state; none → null), serialized string contains `SameSite=Lax` and no `eyJ`.
- [ ] **Step 2: FAIL** → **Step 3: implement `location.ts`** (plain functions, `document`-free so node vitest works).
- [ ] **Step 4: implement `LiveLocationPill`** — pattern-match `coins-balance-pill.tsx`:
  - `"use client"`. State: `loc: LocContext | null` initialised from `parseLocCookie(document.cookie ...)` in a `useEffect` (SSR-safe), then `fetch(contextEndpoint + queryFromCookie)` to reconcile (profile wins server-side); write the reconciled context back to the cookie.
  - Renders `<Modal trigger={<LocationPill>📍 <span className="max-sm:hidden">{locLabel(loc) ?? t("ui.location.set")}</span> ▾</LocationPill>} title={t("ui.location.title")} closeLabel={t("ui.location.close")}>` — Modal is uncontrolled; content: `PincodeInput` (its Find button is INERT by contract — wrap input in a `<form onSubmit={apply}>` and render our own submit `Button`), plus `GpsPill` wired to `navigator.geolocation.getCurrentPosition` (consent = the browser prompt; on grant → `fetch(contextEndpoint?lat&lng)` → apply result).
  - `apply(next: LocContext)`: `document.cookie = serializeLocCookie(next)`; if `isAuthed && next.pincode` → `fetch(profileEndpoint, {method: "PATCH", body: JSON.stringify({pincode: next.pincode}), headers: {"content-type": "application/json"}})` (fire-and-log); then `onChanged ? onChanged(next) : window.location.reload()`. Keyed-ternary the Modal like D11's auto-close idiom so applying closes it.
  - Strings via `useTranslations("ui.location")`; add to all three catalogs (en real; ta/hi best-effort like existing entries): `set` ("Set location"), `title`, `close`, `apply`, `gps` ("📍 Use my location"), `pincodeLabel`, `find`.
  - Styling: existing token classes only (`glass` pill styles come free from `LocationPill`; modal content uses existing Modal primitives). Run `node scripts/check-hex.mjs` to confirm zero raw hex.
- [ ] **Step 5: tests PASS + `pnpm --filter @agri/ui typecheck` (or the package's build/lint script) → commit** `feat(d19): LiveLocationPill + agri_loc cookie lib in @agri/ui`.

---

### Task 9: App wiring — identity BFF proxies + header mounts

**Files:**
- Create: `apps/web-agri/app/api/identity/[...path]/route.ts`, `apps/web-organic/app/api/identity/[...path]/route.ts`, `apps/web-milk/app/api/identity/[...path]/route.ts`
- Modify: `apps/web-agri/app/site-header.tsx`, `apps/web-organic/app/site-header.tsx`, `apps/web-milk/app/site-header.tsx`

**Interfaces:**
- Consumes: `LiveLocationPill` (Task 8), `auth.getAccessToken()` (`@/lib/auth`), backend routes `/identity/location` (public) + `/identity/profile` (authed).
- Produces: guest-capable proxy: `GET|PATCH /api/identity/*` → backend `/identity/*` — attaches bearer when a token exists, forwards WITHOUT one otherwise (public endpoint handles anonymity; backend 401s protected paths on its own). Template = `apps/web-milk/app/api/coins/[...path]/route.ts` with two changes: no hard 401 when token absent; add `PATCH` export.

- [ ] **Step 1: Write one proxy** (web-milk), copying the coins proxy verbatim then:

```ts
const token = await auth.getAccessToken();          // null for guests - fine
const headers: Record<string, string> = {
  ...(token ? { authorization: `Bearer ${token}` } : {}),
  ...(method !== "GET" ? { "content-type": "application/json" } : {}),
};
```

and `export async function PATCH(req, ctx) { return forward(req, ctx.params, "PATCH"); }`. Copy to the other two apps (per-app route files are the accepted duplication — D12 note).
- [ ] **Step 2: Header mounts.** web-agri: replace the hardcoded `location={<LocationPill>📍 <span ...>Coimbatore · 641001</span> ▾</LocationPill>}` with `location={<LiveLocationPill isAuthed={/* from useAgriUser status or leave false + server-detect */} />}`. Simplest correct wiring: `LiveLocationPill` internally calls `/api/auth/me` — NO. Keep it dumb about auth: add an optional `isAuthed` prop default false and have each site-header render it inside the existing client boundary where `useAgriUser` already runs, or pass `isAuthed` from a tiny client wrapper `<HeaderLocation />` colocated in each app that does `const { status } = useAgriUser({ autoSilentSso: false }); return <LiveLocationPill isAuthed={status === "authenticated"} />`. Same for web-organic (its pill shows district only — `locLabel` already handles that). web-milk: ADD the `location` slot with the same `<HeaderLocation />` (extension beyond the mockup, sanctioned by design-system.md line 5 "extend using these tokens" — the milk mockup's pin-hero remains the home-page pattern for D23; exactly ONE switcher per header, satisfying NN#3). web-admin: no location pill (internal tool, no location personalization — deviation from "all apps", recorded in the PR body).
- [ ] **Step 3: Verify visually + e2e-safe.** `pnpm --filter @agri/web-milk dev` (and agri) — header shows pill; switching pincode reloads with new label; guest cookie persists; login → PATCH fires (network tab). Run `npx playwright test e2e/sso.spec.ts` with the stack up (docker compose stop api first if it owns port 8000 — D09 trap) to confirm Login/🪙 locators still pass.
- [ ] **Step 4: `pnpm build` for the three apps (turbo) + check-hex → commit** `feat(d19): one LocationPill switcher wired across storefront headers`.

---

### Task 10: web-milk search page (SearchBar wired to API)

**Files:**
- Create: `apps/web-milk/app/search/page.tsx`
- Create: `apps/web-milk/app/search/search-form.tsx`
- Create: `apps/web-milk/app/api/search/route.ts` — NOT needed; public read goes direct server-side (D16 precedent: public reads bypass the authed BFF). Skip this file.

**Interfaces:**
- Consumes: `SearchBar` (dumb, exists), `readLocationCookie` — add tiny server helper INSIDE page.tsx using `cookies()` + `parseLocCookie` from `@agri/ui`; backend `GET /search?site=milk&...`.
- Produces: `/search?q=...` server-rendered results ordered by location relevance.

- [ ] **Step 1: `search-form.tsx`** — `"use client"`; wraps `SearchBar` in `<form action="/search" method="get">`; `SearchBar` gets `name="q"`, `defaultValue={initialQ}`, `micLabel={t("ui.search.micLabel")}`, placeholder from `ui.search.placeholder`. (Mic/cam stay decorative — mockup parity.)
- [ ] **Step 2: `page.tsx`** — server component:

```tsx
import { cookies } from "next/headers";
import { LOC_COOKIE, parseLocCookie } from "@agri/ui";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string; cursor?: string }> }) {
  const { q = "", cursor } = await searchParams;
  const loc = parseLocCookie((await cookies()).get(LOC_COOKIE)?.value);
  const params = new URLSearchParams({ site: "milk", q });
  if (loc?.pincode) { params.set("pincode", loc.pincode); params.set("covered", "true"); }
  if (cursor) params.set("cursor", cursor);
  const resp = await fetch(`${API}/search?${params}`, { cache: "no-store" });
  const page = resp.ok ? await resp.json() : { items: [], next_cursor: null };
  // render: SearchForm, result cards (name, kind badge, business_name for products,
  // district, verified ✔, price_display), "load more" link with ?q&cursor=next_cursor,
  // empty state via i18n. Tokens only.
}
```

Results card fields come ONLY from `SearchHit` displayed attributes. Cookie read makes the route dynamic automatically (no ISR — per-user location). Add `ui.search.results.*` strings (empty state, verified label, kind labels) to the three catalogs.
- [ ] **Step 3: Manual verify** — stack up, worker running, create an approved milk product via API/fixtures, `curl localhost:8000/search?site=milk&q=milk` shows it, then browser `/search?q=milk` renders it; typo query still hits.
- [ ] **Step 4: `pnpm --filter @agri/web-milk build` + check-hex → commit** `feat(d19): web-milk search page wired to unified search`.

Lighthouse note for the PR body: `scripts/lhci-affected.mjs` audits only home pages (+/demo); `/search` is unaudited pending a seeded-content LHCI fixture — same recorded carve-out as D16's business page. Do NOT silently extend the lhci script here.

---

### Task 11: CI — Meilisearch service container + full gates

**Files:**
- Modify: `.github/workflows/ci.yml` (backend job only)

**Interfaces:** Produces: backend job runs with a live Meili so Tasks 2/3/5 integration tests execute in CI instead of skipping.

- [ ] **Step 1:** Add to the `backend` job's `services:` block (mirror the postgres/redis entries):

```yaml
      meilisearch:
        image: getmeili/meilisearch:v1.13
        ports: ["7700:7700"]
        env:
          MEILI_ENV: development
        options: >-
          --health-cmd "wget --no-verbose --spider http://127.0.0.1:7700/health"
          --health-interval 5s --health-timeout 3s --health-retries 10
```

(127.0.0.1 in the health-cmd — the D01-B IPv6 trap.) Add `MEILISEARCH_URL: http://localhost:7700` to the job env beside `REDIS_URL`. Leave `backend-storm` untouched (no meili tests are slow-marked).
- [ ] **Step 2: Full local gate** from `backend/core`: `ruff format --check . && ruff check . && mypy . && lint-imports && python scripts/migrate_check.py && pytest -q -m "not slow"` → all green. (`migrate_check` wipes dev data — D05 known behavior, acceptable on this branch.) Then `pytest -q -m slow` separately → green.
- [ ] **Step 3: Commit** `ci(d19): meilisearch service container for backend job`.

---

### Task 12: [BG] Coimbatore vendor seed — import-CSV schema + normalizer

**Files:**
- Create: `data/seeds/coimbatore/README.md`
- Create: `data/seeds/coimbatore/businesses.csv`, `branches.csv`, `coverage.csv`, `products.csv`
- Create: `backend/core/scripts/normalize_vendor_seed.py`
- Create: `backend/core/tests/test_vendor_seed.py`

**Interfaces:**
- Produces: the import-CSV contract D27 will load. Columns:
  - `businesses.csv`: `ref,name,type,category_slugs,primary_pincode,description_en,description_ta` (`ref` = stable string key for cross-file joins; loader will mint UUIDv7s)
  - `branches.csv`: `business_ref,address,state,district,pincode,lat,lng` (NO phone/whatsapp columns in the SEED — contact data enters via the claim flow, keeping the seed PII-free)
  - `coverage.csv`: `business_ref,pincode`
  - `products.csv`: `business_ref,vertical_slug,name,specs_json,price_display`
- `normalize_vendor_seed.py`: `python -m scripts.normalize_vendor_seed <raw.csv> --out data/seeds/coimbatore/` — validates and normalizes a raw vendor sheet: pincode must exist in `backend/core/data/geo/pincodes.csv` AND belong to Coimbatore district (lgd 569) or an adjacent allowlist; `type` ∈ business enum; category slugs ∈ seeded set; name whitespace/casing normalized; dedupe by (name, primary_pincode); rejects rows with phone/email-looking content in any field (regex) — writes rejects to `rejects.csv` with reasons.

- [ ] **Step 1: Failing unit tests** for the pure functions (`normalize_row`, `validate_pincode`, `looks_like_pii`) with inline fixture rows — no DB needed.
- [ ] **Step 2: FAIL → implement** (stdlib `csv` only; load the geo CSV once into a dict).
- [ ] **Step 3: Author ~15 starter rows** in the four CSVs: realistic Coimbatore-region dairy vendors (real pincodes 641001–641xxx from the geo file, generic-but-plausible names, `dairy` category, milk products with specs valid against the seeded milk schema). Mark clearly in README: "starter sample — bulk raw data is an owner input before D27; run the normalizer over the raw sheet to regenerate."
- [ ] **Step 4: `pytest tests/test_vendor_seed.py -q` PASS + gate → commit** `feat(d19): coimbatore vendor seed schema + normalizer [bg]`.

---

### Task 13: Final verification + PR

- [ ] **Step 1:** Full backend gate (Task 11 Step 2 commands) + `pnpm turbo run build lint test` at repo root + `node scripts/check-hex.mjs` + e2e sso spec.
- [ ] **Step 2:** NN checklist against running stack: (1) create business via API → visible in `/search` within worker poll interval; (2) location fallback tests green (`pytest tests/test_location_context.py -q`); (3) grep site-headers — exactly one `LiveLocationPill`/`HeaderLocation` per header, none inside AuthCluster; (4) `test_ensure_indexes_and_settings` + `_assert_no_pii` green.
- [ ] **Step 3:** `git status` — zero AM files. Push branch. PR to `dev` titled `feat(d19): search + location` via `git credential fill` token + GitHub API (export the token for child processes). PR body: summary, event-contract table, deviations (web-admin skipped for LocationPill; `claim.approved` realized as `business.updated` alongside existing `business.claimed`; IP fallback dormant until owner provisions an mmdb + `trust_forwarded_for` — VPS-deferred per no-Hostinger policy; `/search` Lighthouse carve-out; image-change events not emitted since media isn't indexed), fast-follows (indexer stall on once-failed event inherits the D12 bus-redelivery gap — same fast-follow; per-app identity proxy copies), and the D22 seam-audit pointers (A3 event table, A4 one-switcher).

## Self-Review (done at write time)

- **Spec coverage:** A indexers+events (T1,3), per-site indexes+coverage-aware (T2,3), delete on soft-delete (tombstone events + T3 delete test; note: no soft-delete code path exists today — the reindex script and null-snapshot handling cover it when one lands), unified search API (T5), B resolution order+persist on profile (T6,7 + existing PATCH), SSR+client exposure (T8 cookie + T10 cookies()), C one header switcher via sibling slots (T8,9), D web-milk SearchBar+location ordering (T10), E seed CSVs (T12). DO-NOTs: Meili only, no PII (tests T1/T2/T3/T5), cursor-not-offset API (T5 opaque cursor; Meili-internal lowercase `"offset"` key documented against the lint gate).
- **Spec deviations (deliberate, PR-documented):** `claim.approved` name → `business.updated` emitted at claim-approve (spec's name doesn't exist on the bus; indexer consumes what producers emit — the D22 A3 check); LocationPill not on web-admin; GPS consent = browser prompt (no separate consent UI); IP rung ships dormant in dev.
- **Type consistency:** `business_event_payload`/`product_event_payload` carry top-level `doc_id` (added in T3 Step 1 back into T1 — implementers of T1 read the Shared Contracts section which now states it); `LocContext`/`locLabel` names match between T8 and T9/T10; `index_uid`/`SITES` consistent T2→T5.
- **Placeholder scan:** T1 Step 1 has two `...` in test bodies with explicit instructions (remaining cases enumerated in prose); T3 delete-test `...` says exactly what to assert; T10 render comment enumerates the fields. Specs `{...}` in T1 product test points at copying valid specs from existing catalog tests — acceptable references to existing code, not TBDs.
