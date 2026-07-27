# D27 Dairy Directory + Brand Pages + Seed — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mount four dairy service categories as pure config on the directory engine, add brand-shaped business pages with "shops near you", load a 150+ Coimbatore vendor/brand seed that provably reaches `covers(641001)` and search, and make Milk.in genuinely 3-locale (en/ta/hi) without regressing static rendering.

**Architecture:** Backend work is all inside `modules/directory` (migration-seeded categories, a `nearby_branches` query beside `covers()`, a new `seed_import` service module driven by a CLI script). Frontend work is all in `apps/web-milk` (next-intl `[locale]` segment with `localePrefix: "as-needed"`, `/c/[category]` landings, category browse on `/[pincode]`, brand variant of the business detail page) plus `packages/ui` (message keys + locale-completeness test).

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend/core, Python 3.12 host venv, no uv), Next.js 15.5.21 + next-intl 4.13.1 + Tailwind 3 (pnpm 11 / Node 24), pytest, vitest (packages/ui), Playwright (root `e2e/`).

**Spec:** `docs/superpowers/specs/2026-07-25-d27-dairy-directory-design.md` (read it first; owner decisions are locked).

## Global Constraints

- NEVER commit to `main` or `dev`. All work on `feat/d27-dairy-directory` (already exists, branched from dev). Conventional commits. PR targets `dev`.
- Backend commands run from `backend/core` with the venv interpreter: `.venv/Scripts/python.exe -m pytest tests/<file> -q` (Windows host). Run test files serially, not with `-n` (parallel pytest shares one DB — known trap).
- After every backend task: `.venv/Scripts/python.exe -m ruff format <changed files>` and `.venv/Scripts/python.exe -m ruff check --fix <changed files>` BEFORE committing (per-task, not end-of-PR — D16 lesson).
- All IDs are UUIDv7 (`uuid6.uuid7()` in migrations). All lists cursor-paginated; OFFSET is banned by a test gate.
- Every new public route needs `public=True` on the SecureRouter decorator AND a line in `backend/core/public_routes.txt` in the same commit (CI diffs the file against the live registry).
- `modules/directory` never imports other modules (import-linter gate). `modules/search` never reads directory tables.
- Frontend: design tokens only — zero raw hex in app code (`check:hex` gate). Match `docs/design-system.md`. Interactive elements need ≥44px tap targets.
- Never log request bodies/query strings in directory module (holds contact PII).
- Frontend checks per task: `pnpm --filter @agri/web-milk typecheck && pnpm --filter @agri/web-milk lint && pnpm --filter @agri/web-milk build`.
- The seed is PII-free by construction: no phone/whatsapp/email anywhere in seed data. `rejects.csv` is gitignored and must never be committed.
- Backend DB for dev/tests: postgres on port 55432 (D03 trap); tests skip visibly when services are down — start docker compose dev stack first if needed.

---

### Task 1: Migration 0026 — four dairy categories + milk-site routing

**Files:**
- Create: `backend/core/alembic/versions/0026_dairy_categories.py`
- Modify: `backend/core/modules/directory/search_sync.py` (CATEGORY_SITES, ~line 34)
- Modify: `backend/core/scripts/normalize_vendor_seed.py` (CATEGORY_SLUGS, ~line 77)
- Modify: `backend/core/data/seeds/coimbatore/README.md` (category list in "Validation" section)
- Test: `backend/core/tests/test_directory_search_sync.py` (append), `backend/core/tests/test_vendor_seed.py` (append)

**Interfaces:**
- Produces: category slugs `veterinarian`, `feed-supplier`, `dairy-farm`, `cooperative` seeded in `directory.categories` with `{en,ta,hi}` names; all four route to the `milk` site index via `CATEGORY_SITES`. Later tasks (5, 8, 10, 12, 13) rely on these exact slugs.

- [ ] **Step 1: Write the failing tests**

Append to `backend/core/tests/test_directory_search_sync.py` (mirror the exact construction style used around line 490 of that file — businesses there are built with `owner_user_id=None`; match the local `business_snapshot`/payload call shape used by neighboring tests):

```python
DAIRY_SERVICE_CATEGORIES = ("veterinarian", "feed-supplier", "dairy-farm", "cooperative")


class TestDairyCategorySites:
    async def test_new_dairy_categories_are_seeded(self, db_session: AsyncSession) -> None:
        rows = (
            await db_session.scalars(
                select(Category.slug).where(Category.slug.in_(DAIRY_SERVICE_CATEGORIES))
            )
        ).all()
        assert sorted(rows) == sorted(DAIRY_SERVICE_CATEGORIES)

    async def test_category_names_are_three_locale(self, db_session: AsyncSession) -> None:
        cats = (
            await db_session.scalars(
                select(Category).where(Category.slug.in_(DAIRY_SERVICE_CATEGORIES))
            )
        ).all()
        for cat in cats:
            name = cat.name if isinstance(cat.name, dict) else cat.name.to_dict()
            assert set(name) >= {"en", "ta", "hi"}, cat.slug
            assert all(v.strip() for v in name.values()), cat.slug

    async def test_veterinarian_business_routes_to_milk_site(
        self, db_session: AsyncSession, tn_geo_sample: None
    ) -> None:
        business = Business(
            owner_user_id=None,
            name="RS Puram Veterinary Clinic",
            slug="rs-puram-veterinary-clinic",
            type="shop",
            primary_pincode="641002",
        )
        db_session.add(business)
        await db_session.flush()
        cat = await db_session.scalar(select(Category).where(Category.slug == "veterinarian"))
        db_session.add(BusinessCategory(business_id=business.id, category_id=cat.id))
        db_session.add(BusinessCoverage(business_id=business.id, pincode="641002"))
        await db_session.flush()
        snapshot = await business_snapshot(db_session, business.id)  # match local call shape
        assert "milk" in snapshot["sites"]
```

Append to `backend/core/tests/test_vendor_seed.py`:

```python
def test_dairy_service_categories_are_valid_seed_slugs() -> None:
    from scripts.normalize_vendor_seed import CATEGORY_SLUGS

    assert {"veterinarian", "feed-supplier", "dairy-farm", "cooperative"} <= CATEGORY_SLUGS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_directory_search_sync.py::TestDairyCategorySites tests/test_vendor_seed.py::test_dairy_service_categories_are_valid_seed_slugs -q`
Expected: FAIL (missing category rows / missing slugs in CATEGORY_SLUGS).

- [ ] **Step 3: Write the migration**

`backend/core/alembic/versions/0026_dairy_categories.py` — mirror 0016's `op.bulk_insert` block exactly (it uses `uuid6.uuid7()` per row, `sa.table` with schema `directory`):

```python
"""D27: dairy service categories (veterinarian, feed-supplier, dairy-farm,
cooperative) - pure config on the D15 directory engine, no new tables."""

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

# (slug, {en,ta,hi}, sort_order) - after 0016's set, which ends at 80.
DAIRY_CATEGORIES = [
    (
        "veterinarian",
        {"en": "Veterinarians", "ta": "கால்நடை மருத்துவர்கள்", "hi": "पशु चिकित्सक"},
        90,
    ),
    (
        "feed-supplier",
        {"en": "Cattle Feed Suppliers", "ta": "கால்நடை தீவனக் கடைகள்", "hi": "पशु आहार विक्रेता"},
        100,
    ),
    ("dairy-farm", {"en": "Dairy Farms", "ta": "பால் பண்ணைகள்", "hi": "डेयरी फ़ार्म"}, 110),
    (
        "cooperative",
        {"en": "Milk Cooperatives", "ta": "பால் கூட்டுறவு சங்கங்கள்", "hi": "दुग्ध सहकारी समितियाँ"},
        120,
    ),
]


def upgrade() -> None:
    op.bulk_insert(
        sa.table(
            "categories",
            sa.column("id", _uuid),
            sa.column("slug", sa.Text),
            sa.column("name", postgresql.JSONB),
            sa.column("sort_order", sa.Integer),
            schema="directory",
        ),
        [
            {"id": uuid6.uuid7(), "slug": slug, "name": name, "sort_order": order}
            for (slug, name, order) in DAIRY_CATEGORIES
        ],
    )


def downgrade() -> None:
    slugs = ", ".join(f"'{slug}'" for (slug, _, _) in DAIRY_CATEGORIES)
    op.execute(f"DELETE FROM directory.categories WHERE slug IN ({slugs})")
```

Check 0016's `name` column value shape first: it inserts `{"en": label}` — the 0026 dict with three locales is the same JSONB column, valid. If `Category.name` is a `Translated` type wrapper, the raw dict insert is still what 0016 does; keep it.

- [ ] **Step 4: Route the categories to the milk site + normalizer allowlist**

In `backend/core/modules/directory/search_sync.py`, extend the existing dict (keep the existing comment style):

```python
CATEGORY_SITES = {
    "dairy": "milk",
    # D27: dairy service categories surface on Milk.in even with no product.
    "veterinarian": "milk",
    "feed-supplier": "milk",
    "dairy-farm": "milk",
    "cooperative": "milk",
}
```

In `backend/core/scripts/normalize_vendor_seed.py`:

```python
CATEGORY_SLUGS = frozenset(
    {"farm", "dairy", "shop", "lab", "nursery", "equipment", "service", "other"}
    # D27 dairy service categories (alembic/versions/0026_dairy_categories.py)
    | {"veterinarian", "feed-supplier", "dairy-farm", "cooperative"}
)
```

Update the README's category bullet to mention both migrations (0016 + 0026) and the four new slugs.

- [ ] **Step 5: Apply migration, run tests**

Run: `cd backend/core && .venv/Scripts/python.exe -m alembic upgrade head` then re-run the Step 2 command.
Expected: PASS. (Test DB gets migrations via conftest's session prep; if the sites test still fails, check the local `business_snapshot` call signature against neighboring tests and adjust the test, not the module.)

- [ ] **Step 6: Format, commit**

```bash
cd backend/core && .venv/Scripts/python.exe -m ruff format alembic/versions/0026_dairy_categories.py modules/directory/search_sync.py scripts/normalize_vendor_seed.py tests/test_directory_search_sync.py tests/test_vendor_seed.py && .venv/Scripts/python.exe -m ruff check --fix <same files>
git add -A && git commit -m "feat(d27): seed dairy service categories + milk-site routing"
```

---

### Task 2: covers() category filter on the public route

**Files:**
- Modify: `backend/core/modules/directory/router.py` (`covers_search`, ~line 520)
- Test: `backend/core/tests/test_directory_router.py` (append near the existing covers tests)

**Interfaces:**
- Consumes: `covers_module.covers(session, *, pincode, cursor, limit, category)` — already supports `category` (`covers.py:135`).
- Produces: `GET /directory/covers/{pincode}?category=<slug>` public API. Task 12's frontend browse and Task 9's integration tests call it.

- [ ] **Step 1: Write the failing test**

Find the existing covers tests in `tests/test_directory_router.py` (search `covers`) and mirror their client/fixture usage exactly (they exercise `GET /directory/covers/{pincode}`). Add:

```python
async def test_covers_category_filter(client, db_session, tn_geo_sample) -> None:
    # one dairy vendor + one veterinarian, both covering 641001
    vendor = Business(
        owner_user_id=None, name="Covers Cat Dairy", slug="covers-cat-dairy",
        type="vendor", primary_pincode="641001",
    )
    vet = Business(
        owner_user_id=None, name="Covers Cat Vet", slug="covers-cat-vet",
        type="shop", primary_pincode="641001",
    )
    db_session.add_all([vendor, vet])
    await db_session.flush()
    vet_cat = await db_session.scalar(select(Category).where(Category.slug == "veterinarian"))
    db_session.add_all([
        BusinessCoverage(business_id=vendor.id, pincode="641001"),
        BusinessCoverage(business_id=vet.id, pincode="641001"),
        BusinessCategory(business_id=vet.id, category_id=vet_cat.id),
    ])
    await db_session.commit()

    response = await client.get("/directory/covers/641001", params={"category": "veterinarian"})
    assert response.status_code == 200
    slugs = [item["slug"] for item in response.json()["items"]]
    assert "covers-cat-vet" in slugs
    assert "covers-cat-dairy" not in slugs


async def test_covers_category_param_validated(client) -> None:
    response = await client.get("/directory/covers/641001", params={"category": "NOT A SLUG!"})
    assert response.status_code == 422
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_directory_router.py -q -k covers_category`
Expected: FAIL — first test returns both businesses (param silently ignored), second returns 200.

- [ ] **Step 3: Forward the param**

In `router.py` `covers_search` (keep everything else identical):

```python
@router.get("/covers/{pincode}", public=True)
async def covers_search(
    pincode: Annotated[str, Path(pattern=r"^\d{6}$")],
    session: SessionDep,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
    category: Annotated[str | None, Query(pattern=r"^[a-z0-9-]{1,40}$")] = None,
) -> CoversOut:
    """Vendor discovery: businesses covering the pincode, nearest first.
    Keyset + rate limit are the scraping defence (no offsets to walk)."""
    try:
        page = await covers_module.covers(
            session, pincode=pincode, cursor=cursor, limit=limit, category=category
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return CoversOut(
        items=[CoversItemOut(**asdict(item)) for item in page.items],
        next_cursor=page.next_cursor,
    )
```

Import `Query` from fastapi if not already imported in the file.

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_directory_router.py -q`
Expected: PASS (whole file — no regressions).

- [ ] **Step 5: Format, commit**

```bash
git add backend/core/modules/directory/router.py backend/core/tests/test_directory_router.py
git commit -m "feat(d27): category filter on public covers route"
```

---

### Task 3: nearby-branches query + public endpoint

**Files:**
- Modify: `backend/core/modules/directory/covers.py` (append the nearby query — it shares `_haversine_m` / `UNLOCATABLE_M`)
- Modify: `backend/core/modules/directory/router.py` (new route + response schemas)
- Modify: `backend/core/public_routes.txt`
- Test: `backend/core/tests/test_directory_router.py` (append)

**Interfaces:**
- Produces: `nearby_branches(session, *, slug, pincode, limit=10) -> list[NearbyBranch] | None` (None = unknown business) and `GET /directory/businesses/{slug}/nearby-branches?pincode=NNNNNN` returning `{"items": [{id, address, district, state, pincode, lat, lng, distance_m}]}`. `lat`/`lng` serialize as strings on the wire (Decimal-wire-string precedent from D24). Task 14's `NearbyShops` component consumes this via the web-milk `/api/directory` proxy.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_directory_router.py`:

```python
class TestNearbyBranches:
    async def _brand(self, db_session) -> Business:
        brand = Business(
            owner_user_id=None, name="Nearby Test Brand", slug="nearby-test-brand",
            type="shop", primary_pincode="641001",
        )
        db_session.add(brand)
        await db_session.flush()
        db_session.add_all([
            # geocoded branch near the 641001 centroid
            Branch(
                business_id=brand.id, address="1 Town Hall Rd", state="Tamil Nadu",
                district="Coimbatore", pincode="641001",
                lat=Decimal("10.9950"), lng=Decimal("76.9610"),
            ),
            # farther geocoded branch
            Branch(
                business_id=brand.id, address="2 Avinashi Rd", state="Tamil Nadu",
                district="Coimbatore", pincode="641004",
                lat=Decimal("11.0290"), lng=Decimal("77.0280"),
            ),
            # ungeocoded branch: falls back to its own pincode centroid
            Branch(
                business_id=brand.id, address="3 Mettupalayam Rd", state="Tamil Nadu",
                district="Coimbatore", pincode="641002", lat=None, lng=None,
            ),
        ])
        await db_session.commit()
        return brand

    async def test_orders_by_distance_and_serves_fallback(
        self, client, db_session, tn_geo_sample
    ) -> None:
        await self._brand(db_session)
        response = await client.get(
            "/directory/businesses/nearby-test-brand/nearby-branches",
            params={"pincode": "641001"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 3
        distances = [item["distance_m"] for item in items]
        assert distances == sorted(distances)
        assert items[0]["address"] == "1 Town Hall Rd"
        # the ungeocoded branch still got a finite distance via its pincode centroid
        ungeo = next(i for i in items if i["address"] == "3 Mettupalayam Rd")
        assert ungeo["distance_m"] < 1_000_000_000

    async def test_unknown_slug_404(self, client, tn_geo_sample) -> None:
        response = await client.get(
            "/directory/businesses/no-such-brand/nearby-branches", params={"pincode": "641001"}
        )
        assert response.status_code == 404

    async def test_unknown_pincode_404(self, client, db_session, tn_geo_sample) -> None:
        await self._brand(db_session)
        response = await client.get(
            "/directory/businesses/nearby-test-brand/nearby-branches",
            params={"pincode": "999999"},
        )
        assert response.status_code == 404

    async def test_pincode_shape_validated(self, client) -> None:
        response = await client.get(
            "/directory/businesses/x/nearby-branches", params={"pincode": "64100"}
        )
        assert response.status_code == 422
```

Use the same `client` fixture name as the rest of the file; `tn_geo_sample` must include centroids for 641001/641002/641004 — check the fixture (conftest ~line 205) and if a pincode is missing pick ones it has (keep three distinct pincodes, one branch ungeocoded).

- [ ] **Step 2: Run to verify failure**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_directory_router.py::TestNearbyBranches -q`
Expected: FAIL 404 (route doesn't exist).

- [ ] **Step 3: Implement the query in covers.py**

Append to `backend/core/modules/directory/covers.py`:

```python
@dataclass(frozen=True, slots=True)
class NearbyBranch:
    id: uuid.UUID
    address: str
    district: str
    state: str
    pincode: str
    lat: Decimal | None
    lng: Decimal | None
    distance_m: int


MAX_NEARBY_BRANCHES = 10

_BRANCH_PINCODE_DISTANCE = _haversine_m("q.lat", "q.lon", "p.centroid_lat", "p.centroid_lon")

_NEARBY_SQL = f"""
WITH q AS (
    SELECT centroid_lat AS lat, centroid_lon AS lon
    FROM geo.pincodes WHERE pincode = :pincode
)
SELECT br.id, br.address, br.district, br.state, br.pincode, br.lat, br.lng,
       CAST(ROUND(COALESCE(
           CASE WHEN br.lat IS NOT NULL AND br.lng IS NOT NULL
                THEN {_BRANCH_DISTANCE} END,
           (SELECT {_BRANCH_PINCODE_DISTANCE}
            FROM geo.pincodes p WHERE p.pincode = br.pincode),
           {UNLOCATABLE_M}
       )) AS BIGINT) AS distance_m
FROM directory.branches br
JOIN directory.businesses b ON b.id = br.business_id
CROSS JOIN q
WHERE b.slug = :slug AND b.status = 'active' AND b.deleted_at IS NULL
  AND br.deleted_at IS NULL
ORDER BY distance_m, br.id
LIMIT :lim
"""


async def nearby_branches(
    session: AsyncSession, *, slug: str, pincode: str, limit: int = MAX_NEARBY_BRANCHES
) -> list[NearbyBranch]:
    """Brand 'shops near you': this business's branches, nearest first.
    Bounded list, no cursor - brands have bounded branch counts and the
    LIMIT caps the response regardless."""
    rows = (
        await session.execute(
            text(_NEARBY_SQL),
            {"slug": slug, "pincode": pincode, "lim": min(limit, MAX_NEARBY_BRANCHES)},
        )
    ).all()
    return [
        NearbyBranch(
            id=m["id"], address=m["address"], district=m["district"], state=m["state"],
            pincode=m["pincode"], lat=m["lat"], lng=m["lng"], distance_m=int(m["distance_m"]),
        )
        for m in (row._mapping for row in rows)
    ]
```

- [ ] **Step 4: Implement the route**

In `router.py` (near `covers_search`; mirror `CoversItemOut`'s Decimal-to-string wire handling for lat/lng — copy how that schema declares them):

```python
class NearbyBranchOut(BaseModel):
    id: uuid.UUID
    address: str
    district: str
    state: str
    pincode: str
    lat: Decimal | None
    lng: Decimal | None
    distance_m: int


class NearbyBranchesOut(BaseModel):
    items: list[NearbyBranchOut]


@router.get("/businesses/{slug}/nearby-branches", public=True)
async def nearby_branches_route(
    slug: str,
    pincode: Annotated[str, Query(pattern=r"^\d{6}$")],
    session: SessionDep,
) -> NearbyBranchesOut:
    """Brand page 'shops near you' (D27.B): 404s are explicit so the page can
    distinguish bad slug / unknown pincode from a brand with no branches."""
    known_business = await session.scalar(
        select(Business.id).where(
            Business.slug == slug, Business.status == "active", Business.deleted_at.is_(None)
        )
    )
    if known_business is None:
        raise HTTPException(status_code=404, detail="Business not found")
    known_pincode = await session.scalar(
        text("SELECT 1 FROM geo.pincodes WHERE pincode = :p"), {"p": pincode}
    )
    if known_pincode is None:
        raise HTTPException(status_code=404, detail="Unknown pincode")
    items = await covers_module.nearby_branches(session, slug=slug, pincode=pincode)
    return NearbyBranchesOut(items=[NearbyBranchOut(**asdict(item)) for item in items])
```

Adjust the raw-`text` scalar call to the file's local style (it may already have a geo-pincode existence helper — search `geo.pincodes` in the module and reuse if one exists).

Add to `backend/core/public_routes.txt` (keep the commented style):

```
# /directory/businesses/{slug}/nearby-branches: brand-page "shops near you"
# (D27.B) - branch addresses are already public on the business page; no
# contact fields in the response; bounded LIMIT 10, no cursor to walk.
/directory/businesses/{slug}/nearby-branches
```

- [ ] **Step 5: Run tests to verify pass**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_directory_router.py -q` and `.venv/Scripts/python.exe scripts/dump_public_routes.py --check`
Expected: both PASS.

- [ ] **Step 6: Format, commit**

```bash
git add backend/core/modules/directory/covers.py backend/core/modules/directory/router.py backend/core/public_routes.txt backend/core/tests/test_directory_router.py
git commit -m "feat(d27): public nearby-branches endpoint for brand pages"
```

---

### Task 4: seed contract gains description_hi

**Files:**
- Modify: `backend/core/scripts/normalize_vendor_seed.py`
- Modify: `backend/core/data/seeds/coimbatore/businesses.csv` (add column + 15 Hindi values)
- Modify: `backend/core/data/seeds/coimbatore/README.md` (contract table)
- Test: `backend/core/tests/test_vendor_seed.py`

**Interfaces:**
- Produces: `businesses.csv` header becomes `ref,name,type,category_slugs,primary_pincode,description_en,description_ta,description_hi`. Task 7's `load_bundle` and Task 10's dataset depend on this exact header.

- [ ] **Step 1: Write the failing test**

In `tests/test_vendor_seed.py`, find `TestStarterSeed` (it asserts the shipped CSV headers/rows). Update the expected `businesses.csv` header there to include `description_hi`, and add:

```python
def test_businesses_csv_has_hindi_descriptions() -> None:
    with (SEED_DIR / "businesses.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "starter sample must not be empty"
    for row in rows:
        assert "description_hi" in row
        assert row["description_hi"].strip(), row["ref"]
```

Also update any `_row(...)` base-dict / normalize_row expectations in the file that enumerate description fields to include `description_hi` (empty-string default in the raw row is fine — mirror how `description_ta` is treated).

- [ ] **Step 2: Run to verify failure**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_vendor_seed.py -q`
Expected: FAIL (missing column).

- [ ] **Step 3: Extend the normalizer**

In `scripts/normalize_vendor_seed.py`, make these mechanical changes (read the file top to bottom first — it's ~17KB of pure functions):
1. Module docstring: add `description_hi` to both the raw-input contract line (after `description_ta`) and the `businesses.csv` output contract line.
2. Wherever the raw row's `description_ta` is read/normalized (in `normalize_row`), do the same for `description_hi` (blank allowed on raw input).
3. Add `description_hi` to `_PII_CHECKED_FIELDS`.
4. Add `description_hi` to the `businesses.csv` writer header and row emission (after `description_ta`).
5. If a `NormalizedBusiness`-style dataclass exists, add the field there.

- [ ] **Step 4: Add Hindi to the starter sample**

Edit `data/seeds/coimbatore/businesses.csv`: append `description_hi` to the header and a non-empty Hindi description to each of the 15 rows — faithful translations of that row's `description_en` (e.g. `Fresh cow milk daily doorstep delivery` → `ताज़ा गाय का दूध, रोज़ घर पर डिलीवरी`). No phone/email shapes. Update the README contract table row for `businesses.csv`.

- [ ] **Step 5: Run tests to verify pass**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_vendor_seed.py -q`
Expected: PASS.

- [ ] **Step 6: Format, commit**

```bash
git add backend/core/scripts/normalize_vendor_seed.py backend/core/data/seeds/coimbatore/businesses.csv backend/core/data/seeds/coimbatore/README.md backend/core/tests/test_vendor_seed.py
git commit -m "feat(d27): seed contract gains description_hi (3-locale seeded content)"
```

---

### Task 5: normalizer multi-row merge (multi-branch / multi-product brands)

**Files:**
- Modify: `backend/core/scripts/normalize_vendor_seed.py`
- Modify: `backend/core/data/seeds/coimbatore/README.md` (raw-input contract note)
- Test: `backend/core/tests/test_vendor_seed.py`

**Interfaces:**
- Produces: raw sheets may carry an optional `ref` column; rows sharing a non-blank `ref` merge into ONE business — first row is canonical for business fields, every row may contribute a branch (when address/pincode present) and a product (when vertical_slug present); coverage pincodes union. Task 10's brand rows (Aavin with 12 parlours) require this. Output contract (4 CSVs) is unchanged — `branches.csv`/`products.csv` already allow multiple rows per `business_ref`.

- [ ] **Step 1: Write the failing tests**

```python
class TestMultiRowMerge:
    def test_shared_ref_merges_branches_and_products(self) -> None:
        rows = [
            _row(
                ref="aavin-cbe", name="Aavin Coimbatore", type="shop",
                address="Parlour 1, Town Hall", pincode="641001",
                product_name="Aavin Toned Milk", milk_type="toned",
                coverage_pincodes="641001",
            ),
            _row(
                ref="aavin-cbe", name="Aavin Coimbatore", type="shop",
                address="Parlour 2, RS Puram", pincode="641002",
                product_name="Aavin Full Cream", milk_type="cow",
                coverage_pincodes="641002",
            ),
        ]
        merged = merge_rows(rows)  # new pure function under test
        assert len(merged) == 1
        business = merged[0]
        assert len(business.branches) == 2
        assert len(business.products) == 2
        assert set(business.coverage_pincodes) == {"641001", "641002"}

    def test_blank_ref_rows_stay_separate_and_dupes_still_reject(self) -> None:
        rows = [_row(), _row()]  # same (name, primary_pincode), no ref
        merged = merge_rows(rows)
        assert len(merged) == 1  # second is a duplicate → handled by existing dedupe
```

Shape the assertions to the normalizer's actual intermediate types once read — the REQUIRED behavior is: one output `businesses.csv` row per ref-group, N `branches.csv` rows, N `products.csv` rows, unioned coverage; and ref-less behavior byte-identical to today (existing tests must stay green). Add `ref: ""` to the `_row()` base dict.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_vendor_seed.py -q -k MultiRowMerge`
Expected: FAIL (`merge_rows` doesn't exist).

- [ ] **Step 3: Implement `merge_rows`**

Add a pure function between row-normalization and dedupe in the normalizer pipeline:

```python
def merge_rows(rows: Sequence[dict[str, str]]) -> list[...]:
    """Group raw rows by non-blank `ref`: first row is canonical for the
    business fields; each row contributes its branch (when address/pincode
    present) and product (when vertical_slug non-blank); coverage is the
    union. Ref-less rows pass through one-per-business exactly as before
    (dedupe still rejects accidental duplicates)."""
```

Wire it into `main()`'s pipeline; the emitted CSVs write one branches/products row per contribution with the business's `ref`. If a ref-group's rows disagree on `name`/`type`/`primary_pincode`, reject the group with reason `ref_conflict:<field>` (into rejects.csv) — silent divergence is how bad seed data slips in. Document the `ref` column in the module docstring and README raw-input section.

- [ ] **Step 4: Run the whole seed test file**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_vendor_seed.py -q`
Expected: PASS, including all pre-existing tests (proves ref-less behavior unchanged).

- [ ] **Step 5: Format, commit**

```bash
git add backend/core/scripts/normalize_vendor_seed.py backend/core/data/seeds/coimbatore/README.md backend/core/tests/test_vendor_seed.py
git commit -m "feat(d27): normalizer ref-grouped rows for multi-branch brands"
```

---

### Task 6: i18n foundation — glossary, locale-completeness gate, D27 message keys

**Files:**
- Create: `docs/i18n-glossary.md`
- Create: `packages/ui/src/i18n/locale-completeness.test.ts`
- Modify: `packages/ui/src/i18n/messages/en.json`, `ta.json`, `hi.json`

**Interfaces:**
- Produces: message namespaces `ui.dairyCategories.{veterinarian|feedSupplier|dairyFarm|cooperative}.{name,description}`, `ui.categoryBrowse.{heading,empty,allMilk}`, `ui.brandPage.{products,shopsNearYou,pincodeLabel,find,empty,kmAway}`, `ui.localeSwitcher.label` — Tasks 12–14 consume these exact keys. The vitest gate fails CI on ANY key-set or empty-value drift across locales (non-negotiable #2).

- [ ] **Step 1: Write the completeness test (it should PASS against current catalogs — it's a gate, not a bug hunt)**

`packages/ui/src/i18n/locale-completeness.test.ts` (mirror the test-file conventions of existing tests in `packages/ui/src`, e.g. the `seo/meta` or `location` tests):

```ts
import { describe, expect, it } from "vitest";

import en from "./messages/en.json";
import hi from "./messages/hi.json";
import ta from "./messages/ta.json";

function flatten(node: unknown, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  if (typeof node === "string") {
    out.set(prefix, node);
    return out;
  }
  if (node && typeof node === "object") {
    for (const [key, value] of Object.entries(node)) {
      for (const [childKey, childValue] of flatten(value, prefix ? `${prefix}.${key}` : key)) {
        out.set(childKey, childValue);
      }
    }
  }
  return out;
}

const catalogs = { en: flatten(en), ta: flatten(ta), hi: flatten(hi) } as const;

describe("locale completeness (D27 non-negotiable #2)", () => {
  it.each(["ta", "hi"] as const)("%s has exactly en's key set", (locale) => {
    expect([...catalogs[locale].keys()].sort()).toEqual([...catalogs.en.keys()].sort());
  });

  it.each(["en", "ta", "hi"] as const)("%s has no empty values", (locale) => {
    const empty = [...catalogs[locale]].filter(([, v]) => v.trim() === "").map(([k]) => k);
    expect(empty).toEqual([]);
  });
});
```

Run: `pnpm --filter @agri/ui test`
Expected: PASS. If it FAILS, the catalogs have real drift — fix the missing/empty keys as part of this step (that is the point of the gate).

- [ ] **Step 2: Write the glossary**

`docs/i18n-glossary.md` — canonical trilingual terms; every D27 string and seeded description must use these renderings. Seed it with (extend to ~25 rows using existing catalog translations and geo `name_ta` as sources):

```markdown
# Milk.in / Agri i18n glossary (D27)

Canonical en → ta → hi renderings. New UI strings and seeded content MUST
use these; deviations are review findings. Sources: packages/ui catalogs,
data/geo name_ta columns, milk spec-schema labels (0018 migration).

| en | ta | hi |
|---|---|---|
| milk | பால் | दूध |
| vendor | விற்பனையாளர் | विक्रेता |
| dairy | பால் பண்ணை நிறுவனம் | डेयरी |
| dairy farm | பால் பண்ணை | डेयरी फ़ार्म |
| veterinarian | கால்நடை மருத்துவர் | पशु चिकित्सक |
| cattle feed | கால்நடை தீவனம் | पशु आहार |
| cooperative | கூட்டுறவு சங்கம் | सहकारी समिति |
| brand | பிராண்ட் | ब्रांड |
| shop | கடை | दुकान |
| pincode | பின்கோடு | पिनकोड |
| delivery | டெலிவரி | डिलीवरी |
| fresh | புதிய | ताज़ा |
| cow milk | பசும்பால் | गाय का दूध |
| buffalo milk | எருமைப்பால் | भैंस का दूध |
| near you | உங்களருகில் | आपके पास |
```

Cross-check `ta`/`hi` renderings against the existing catalogs (e.g. `ui.search` strings) so the glossary codifies what's already shipped rather than contradicting it.

- [ ] **Step 3: Add the D27 keys to all three catalogs**

Add to `en.json` under `ui` (then translate into `ta.json`/`hi.json` glossary-consistently — never leave a key English in ta/hi):

```json
"dairyCategories": {
  "veterinarian": {
    "name": "Veterinarians",
    "description": "Find veterinary clinics for your cattle — vaccinations, treatment and farm visits."
  },
  "feedSupplier": {
    "name": "Cattle Feed Suppliers",
    "description": "Shops selling cattle feed, fodder and supplements near you."
  },
  "dairyFarm": {
    "name": "Dairy Farms",
    "description": "Local dairy farms producing fresh milk in your area."
  },
  "cooperative": {
    "name": "Milk Cooperatives",
    "description": "Milk cooperative societies collecting and selling milk locally."
  },
  "browseCta": "Find near your pincode"
},
"categoryBrowse": {
  "heading": "{category} in {place}",
  "empty": "Nothing listed here yet — check back soon.",
  "allMilk": "All milk"
},
"brandPage": {
  "products": "Products",
  "shopsNearYou": "Shops near you",
  "pincodeLabel": "Your pincode",
  "find": "Find shops",
  "empty": "No shops found near {pincode}.",
  "kmAway": "{km} km away"
},
"localeSwitcher": { "label": "Language" }
```

Run: `pnpm --filter @agri/ui test` — the completeness gate now enforces the ta/hi translations exist.

- [ ] **Step 4: Commit**

```bash
git add docs/i18n-glossary.md packages/ui/src/i18n/
git commit -m "feat(d27): i18n glossary, locale-completeness gate, D27 message keys"
```

---

### Task 7: seed_import — bundle loading + contract validation (pure, no DB)

**Files:**
- Create: `backend/core/modules/directory/seed_import.py`
- Test: `backend/core/tests/test_seed_import.py`

**Interfaces:**
- Produces (Task 8/9 consume these exact names):

```python
class SeedContractError(Exception): ...          # message lists every violation

@dataclass(frozen=True, slots=True)
class SeedBranch:
    address: str; state: str; district: str; pincode: str
    lat: Decimal | None; lng: Decimal | None

@dataclass(frozen=True, slots=True)
class SeedProduct:
    vertical_slug: str; name: str; specs: dict[str, Any]; price_display: str | None

@dataclass(frozen=True, slots=True)
class SeedBusiness:
    ref: str; name: str; type: str; category_slugs: tuple[str, ...]
    primary_pincode: str; description: dict[str, str]      # {en,ta,hi}, blanks dropped
    branches: tuple[SeedBranch, ...]; coverage: tuple[str, ...]
    products: tuple[SeedProduct, ...]

def load_bundle(seed_dir: Path) -> list[SeedBusiness]      # raises SeedContractError
```

- [ ] **Step 1: Write the failing tests**

`backend/core/tests/test_seed_import.py`:

```python
"""D27: seed bundle loading (pure) + DB import (Task 8 adds the DB class)."""

from decimal import Decimal
from pathlib import Path

import pytest

from modules.directory.seed_import import SeedContractError, load_bundle

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seeds" / "coimbatore"


def _write_bundle(tmp_path: Path, **overrides: str) -> Path:
    files = {
        "businesses.csv": (
            "ref,name,type,category_slugs,primary_pincode,description_en,description_ta,description_hi\n"
            'b1,Test Dairy,vendor,dairy,641001,Fresh milk,புதிய பால்,ताज़ा दूध\n'
        ),
        "branches.csv": (
            "business_ref,address,state,district,pincode,lat,lng\n"
            "b1,1 Main Rd,Tamil Nadu,Coimbatore,641001,10.99,76.96\n"
        ),
        "coverage.csv": "business_ref,pincode\nb1,641001\n",
        "products.csv": (
            "business_ref,vertical_slug,name,specs_json,price_display\n"
            'b1,milk,Fresh Cow Milk,"{""milk_type"": ""cow""}",₹32/500ml\n'
        ),
    }
    files.update(overrides)
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path


class TestLoadBundle:
    def test_loads_starter_sample(self) -> None:
        bundle = load_bundle(SEED_DIR)
        assert len(bundle) >= 15
        first = bundle[0]
        assert first.branches and first.coverage
        assert set(first.description) >= {"en"}

    def test_happy_path_shapes(self, tmp_path: Path) -> None:
        [business] = load_bundle(_write_bundle(tmp_path))
        assert business.ref == "b1"
        assert business.branches[0].lat == Decimal("10.99")
        assert business.products[0].specs == {"milk_type": "cow"}
        assert business.description == {
            "en": "Fresh milk", "ta": "புதிய பால்", "hi": "ताज़ा दूध"
        }

    def test_orphan_branch_ref_rejected(self, tmp_path: Path) -> None:
        seed_dir = _write_bundle(
            tmp_path,
            **{"branches.csv": (
                "business_ref,address,state,district,pincode,lat,lng\n"
                "GHOST,1 Main Rd,Tamil Nadu,Coimbatore,641001,,\n"
            )},
        )
        with pytest.raises(SeedContractError, match="GHOST"):
            load_bundle(seed_dir)

    def test_bad_pincode_rejected(self, tmp_path: Path) -> None:
        seed_dir = _write_bundle(
            tmp_path,
            **{"coverage.csv": "business_ref,pincode\nb1,64100\n"},
        )
        with pytest.raises(SeedContractError, match="64100"):
            load_bundle(seed_dir)

    def test_bad_type_rejected(self, tmp_path: Path) -> None:
        seed_dir = _write_bundle(
            tmp_path,
            **{"businesses.csv": (
                "ref,name,type,category_slugs,primary_pincode,description_en,description_ta,description_hi\n"
                "b1,Test Dairy,supermarket,dairy,641001,Fresh milk,,\n"
            )},
        )
        with pytest.raises(SeedContractError, match="supermarket"):
            load_bundle(seed_dir)

    def test_business_without_branch_rejected(self, tmp_path: Path) -> None:
        seed_dir = _write_bundle(
            tmp_path, **{"branches.csv": "business_ref,address,state,district,pincode,lat,lng\n"}
        )
        with pytest.raises(SeedContractError, match="b1"):
            load_bundle(seed_dir)

    def test_bad_specs_json_rejected(self, tmp_path: Path) -> None:
        seed_dir = _write_bundle(
            tmp_path,
            **{"products.csv": (
                "business_ref,vertical_slug,name,specs_json,price_display\n"
                "b1,milk,Broken,not-json,\n"
            )},
        )
        with pytest.raises(SeedContractError, match="not-json|specs"):
            load_bundle(seed_dir)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_seed_import.py -q`
Expected: FAIL (module doesn't exist).

- [ ] **Step 3: Implement**

`backend/core/modules/directory/seed_import.py` — module docstring explains the D27 contract and that businesses import ownerless (claimable, D16). Implementation outline (complete it —every rule below is required):

```python
PINCODE_RE = re.compile(r"^\d{6}$")
BUSINESS_TYPES = frozenset({"vendor", "shop", "lab", "farm"})
REQUIRED_HEADERS = {
    "businesses.csv": [
        "ref", "name", "type", "category_slugs", "primary_pincode",
        "description_en", "description_ta", "description_hi",
    ],
    "branches.csv": ["business_ref", "address", "state", "district", "pincode", "lat", "lng"],
    "coverage.csv": ["business_ref", "pincode"],
    "products.csv": ["business_ref", "vertical_slug", "name", "specs_json", "price_display"],
}


def load_bundle(seed_dir: Path) -> list[SeedBusiness]:
    """Parse + validate the four contract CSVs. Collects ALL violations and
    raises one SeedContractError listing them (a 150-row import must report
    every problem in one run, not one per run)."""
```

Rules: exact headers per file (order-insensitive is fine, missing/extra column = violation); every `business_ref` in branches/coverage/products must exist in businesses (`orphan ref`); every business needs ≥1 branch and ≥1 coverage pincode; `ref` and `(name, primary_pincode)` unique; pincodes match `PINCODE_RE`; `type` in `BUSINESS_TYPES`; `specs_json` must parse as a JSON object (schema validation itself happens in Task 8 against the live DB schema); lat/lng blank→`None` else `Decimal`; description dict drops blank locales but requires `en`; coverage per business ≤500 (`service.MAX_COVERAGE_PINCODES` — import the constant). Category slug validity is checked in Task 8 against the DB (the categories table is the source of truth, not a hardcoded list).

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_seed_import.py tests/test_vendor_seed.py -q`
Expected: PASS.

- [ ] **Step 5: Format, commit**

```bash
git add backend/core/modules/directory/seed_import.py backend/core/tests/test_seed_import.py
git commit -m "feat(d27): seed bundle loader with full contract validation"
```

---

### Task 8: seed_import — idempotent DB import + product-builder refactor

**Files:**
- Modify: `backend/core/modules/directory/catalog_service.py` (extract `_build_product`)
- Modify: `backend/core/modules/directory/seed_import.py` (add import functions)
- Test: `backend/core/tests/test_seed_import.py` (append), existing `tests/test_catalog_*.py` must stay green

**Interfaces:**
- Consumes: `load_bundle` (Task 7), `service._slugify`/`service._free_slug`, `search_sync.business_event_payload`/`product_event_payload`.
- Produces:

```python
@dataclass(frozen=True, slots=True)
class ImportOutcome:
    ref: str
    action: str            # "created" | "skipped"
    business_id: uuid.UUID

@dataclass(frozen=True, slots=True)
class ImportReport:
    outcomes: list[ImportOutcome]
    event_payloads: list[tuple[str, dict]]   # (event_type, payload) — publish AFTER commit
    @property
    def created(self) -> int: ...
    @property
    def skipped(self) -> int: ...

async def import_seed(session: AsyncSession, bundle: list[SeedBusiness]) -> ImportReport
```

Also: `catalog_service._build_product(session, *, business_id, vertical_slug, name, specs, price_display) -> Product` — the post-IDOR-gate body of `create_product`, now shared. Task 9's CLI consumes `import_seed`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_seed_import.py`:

```python
from modules.directory.seed_import import import_seed


def _sample_bundle() -> list[SeedBusiness]:
    """Two businesses on tn_geo_sample pincodes: a vet (no products) and a
    dairy vendor (one milk product)."""
    return [
        SeedBusiness(
            ref="vet-1", name="Seed Vet Clinic", type="shop",
            category_slugs=("veterinarian",), primary_pincode="641001",
            description={"en": "Cattle vet", "ta": "கால்நடை மருத்துவர்", "hi": "पशु चिकित्सक"},
            branches=(SeedBranch(
                address="5 Trichy Rd", state="Tamil Nadu", district="Coimbatore",
                pincode="641001", lat=None, lng=None,
            ),),
            coverage=("641001",), products=(),
        ),
        SeedBusiness(
            ref="dairy-1", name="Seed Fresh Dairy", type="vendor",
            category_slugs=("dairy",), primary_pincode="641001",
            description={"en": "Fresh milk"},
            branches=(SeedBranch(
                address="6 Trichy Rd", state="Tamil Nadu", district="Coimbatore",
                pincode="641001", lat=Decimal("10.99"), lng=Decimal("76.96"),
            ),),
            coverage=("641001",),
            products=(SeedProduct(
                vertical_slug="milk", name="Fresh Cow Milk",
                specs={"milk_type": "cow", "fat_percent": 4.2}, price_display="₹32/500ml",
            ),),
        ),
    ]


class TestImportSeed:
    async def test_creates_ownerless_claimable_businesses(
        self, db_session, tn_geo_sample
    ) -> None:
        report = await import_seed(db_session, _sample_bundle())
        assert report.created == 2 and report.skipped == 0
        vet = await db_session.scalar(
            select(Business).where(Business.name == "Seed Vet Clinic")
        )
        assert vet.owner_user_id is None            # claimable (D16)
        assert vet.status == "active"
        cats = (
            await db_session.scalars(
                select(Category.slug)
                .join(BusinessCategory, BusinessCategory.category_id == Category.id)
                .where(BusinessCategory.business_id == vet.id)
            )
        ).all()
        assert cats == ["veterinarian"]

    async def test_products_created_approved_with_pinned_schema(
        self, db_session, tn_geo_sample
    ) -> None:
        await import_seed(db_session, _sample_bundle())
        product = await db_session.scalar(
            select(Product).join(Business, Business.id == Product.business_id)
            .where(Business.name == "Seed Fresh Dairy")
        )
        assert product.moderation_status == "approved"
        assert product.vertical_slug == "milk"
        assert product.schema_version is not None

    async def test_reimport_is_idempotent(self, db_session, tn_geo_sample) -> None:
        first = await import_seed(db_session, _sample_bundle())
        assert first.created == 2
        await db_session.flush()
        second = await import_seed(db_session, _sample_bundle())
        assert second.created == 0 and second.skipped == 2
        count = await db_session.scalar(
            select(func.count()).select_from(Business).where(
                Business.name.in_(["Seed Vet Clinic", "Seed Fresh Dairy"])
            )
        )
        assert count == 2

    async def test_event_payloads_captured_for_created_only(
        self, db_session, tn_geo_sample
    ) -> None:
        first = await import_seed(db_session, _sample_bundle())
        types = [t for (t, _) in first.event_payloads]
        assert types.count("business.created") == 2
        assert types.count("product.created") == 1
        await db_session.flush()
        second = await import_seed(db_session, _sample_bundle())
        assert second.event_payloads == []

    async def test_unknown_category_slug_fails_loud(self, db_session, tn_geo_sample) -> None:
        bad = [replace(_sample_bundle()[0], ref="x", name="X Clinic",
                       category_slugs=("no-such-category",))]
        with pytest.raises(SeedContractError, match="no-such-category"):
            await import_seed(db_session, bad)
```

(Imports: `replace` from dataclasses, `func` from sqlalchemy, plus model imports mirroring the file's existing ones. Products need the milk vertical + spec schema seeded — migration 0018 did that; the test DB has it.)

- [ ] **Step 2: Run to verify failure**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_seed_import.py -q`
Expected: TestImportSeed FAILS (`import_seed` undefined); TestLoadBundle stays green.

- [ ] **Step 3: Extract `_build_product` in catalog_service**

Read `catalog_service.create_product` (line ~112) end to end. Move everything AFTER the `get_owned_business` IDOR gate (vertical lookup, active-schema lookup, spec validation, Product construction incl. slug minting, flush) into:

```python
async def _build_product(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    vertical_slug: str,
    name: str,
    specs: dict[str, Any],
    price_display: str | None = None,
) -> Product:
    """Shared post-authorization product construction: create_product (owner
    API) and seed_import (D27 ownerless seed) both build products through
    this one path so spec pinning/validation can never diverge."""
```

`create_product` becomes: IDOR gate, then `return await _build_product(...)`. Run `.venv/Scripts/python.exe -m pytest tests -q -k catalog` — all existing catalog tests must stay green before continuing.

- [ ] **Step 4: Implement `import_seed`**

In `seed_import.py`:

```python
async def import_seed(session: AsyncSession, bundle: list[SeedBusiness]) -> ImportReport:
    # 1. Resolve every category slug used by the bundle in ONE query;
    #    unknown slug -> SeedContractError (DB is the source of truth).
    # 2. Per business:
    #    existing = await session.scalar(
    #        select(Business.id).where(
    #            Business.name == seed.name,
    #            Business.primary_pincode == seed.primary_pincode,
    #            Business.deleted_at.is_(None),
    #        )
    #    )
    #    -> "skipped" outcome when found (idempotency key = the normalizer's
    #       own dedupe key; no schema change).
    #    Otherwise construct ownerless rows through the real helpers:
    #    business = Business(
    #        owner_user_id=None,                      # claimable, D16
    #        name=seed.name,
    #        slug=await _free_slug(session, _slugify(seed.name)),
    #        type=seed.type,
    #        primary_pincode=seed.primary_pincode,
    #        description=Translated.from_dict(seed.description),
    #    )
    #    session.add(business); await session.flush()
    #    add Branch / BusinessCoverage / BusinessCategory rows;
    #    for each product: product = await catalog_service._build_product(...)
    #                      await catalog_service.moderate_product(
    #                          session, product_id=product.id, approve=True)
    # 3. After all creations: flush, then capture fat-event payloads for
    #    CREATED rows only (before any commit - ORM attrs expire on commit):
    #    ("business.created", await business_event_payload(session, bid))
    #    ("product.created", await product_event_payload(session, pid))
    # 4. Return ImportReport. NEVER commit here - the caller owns the
    #    commit/rollback (CLI dry-run relies on it).
```

Import `_free_slug`, `_slugify` from `modules.directory.service` and `Translated` from `shared.i18n` (match `service.py`'s own import). The `# noqa` / private-import from a sibling file in the same module is fine; if lint complains, re-export them in `service.py` as `slugify_name`/`free_slug` and use those names in both places.

- [ ] **Step 5: Run tests to verify pass**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_seed_import.py -q` then `-k catalog` again.
Expected: all PASS.

- [ ] **Step 6: Format, commit**

```bash
git add backend/core/modules/directory/seed_import.py backend/core/modules/directory/catalog_service.py backend/core/tests/test_seed_import.py
git commit -m "feat(d27): idempotent ownerless seed import via shared product builder"
```

---

### Task 9: CLI script + covers(641001) and search-index proof

**Files:**
- Create: `backend/core/scripts/import_vendor_seed.py`
- Test: `backend/core/tests/test_seed_import.py` (append)

**Interfaces:**
- Consumes: `load_bundle`, `import_seed`, `shared.events.publish`, `covers()`, `modules.search.indexing.apply_event`.
- Produces: `python -m scripts.import_vendor_seed [--seed-dir data/seeds/coimbatore] [--dry-run]` — the tool Task 15 runs for the real load.

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/test_seed_import.py`:

```python
class TestSeedReachesSurfaces:
    async def test_seeded_vendors_appear_in_covers_641001(
        self, db_session, tn_geo_sample
    ) -> None:
        await import_seed(db_session, _sample_bundle())
        await db_session.flush()
        page = await covers(db_session, pincode="641001")
        names = {item.name for item in page.items}
        assert {"Seed Vet Clinic", "Seed Fresh Dairy"} <= names

    async def test_covers_category_filter_on_seeded_vet(
        self, db_session, tn_geo_sample
    ) -> None:
        await import_seed(db_session, _sample_bundle())
        await db_session.flush()
        page = await covers(db_session, pincode="641001", category="veterinarian")
        names = {item.name for item in page.items}
        assert "Seed Vet Clinic" in names
        assert "Seed Fresh Dairy" not in names

    async def test_seed_events_index_into_meili(
        self, db_session, tn_geo_sample, meili
    ) -> None:
        """The classic stale-index seam (spec NN#1): prove the captured
        payloads actually become milk-site documents."""
        report = await import_seed(db_session, _sample_bundle())
        await db_session.flush()
        for event_type, payload in report.event_payloads:
            await apply_event(event_type, payload)   # match apply_event's real signature
        # then search/assert the business doc exists on the milk index —
        # mirror the existing meili-backed assertions in
        # tests/test_search_indexing.py (index name + client access) exactly.
```

Complete the last test by copying the meili client/index access used in the existing search-indexing tests (search `meili` in tests/ — the fixture at conftest ~line 191 skips visibly when Meili is down). `apply_event`'s exact signature is at `modules/search/indexing.py:103` — adapt the call, not the intent: assert a document for "Seed Vet Clinic" is retrievable from the milk site index.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_seed_import.py::TestSeedReachesSurfaces -q`
Expected: FAIL (imports missing / assertions unmet) — then fix imports so only genuine behavior is being tested.

- [ ] **Step 3: Make the surface tests pass**

These should pass with Task 8's implementation once imports are correct (`from modules.directory.covers import covers`, `from modules.search.indexing import apply_event`). If the vet business does NOT appear in covers, debug the import (coverage rows missing?) — do not weaken assertions. Note: tests importing from BOTH `modules.directory` and `modules.search` are fine (tests aren't under import-linter's module-independence contracts — confirm by the existing cross-module e2e tests like `test_d22_loop_e2e.py`).

- [ ] **Step 4: Write the CLI**

`backend/core/scripts/import_vendor_seed.py`:

```python
"""D27 bulk import: load data/seeds/coimbatore/*.csv into the directory.

    cd backend/core
    python -m scripts.import_vendor_seed            # real import + publish
    python -m scripts.import_vendor_seed --dry-run  # validate + report, rollback

Idempotent: reruns skip existing (name, primary_pincode) matches. Creates
OWNERLESS businesses (claimable via the D16 flow). Publishes fat-event
snapshots after commit so the D19 search worker indexes them (worker must
be running; scripts/reindex_search.py is the recovery path).
This is a careful one-off loader, NOT the D63 pipeline.
"""

import argparse
import asyncio
from pathlib import Path

from modules.directory.seed_import import SeedContractError, import_seed, load_bundle
from shared.db import get_sessionmaker
from shared.events import publish


async def run(seed_dir: Path, *, dry_run: bool) -> int:
    try:
        bundle = load_bundle(seed_dir)
    except SeedContractError as exc:
        print(f"CONTRACT VIOLATIONS - nothing imported:\n{exc}")  # noqa: T201 - CLI output
        return 1
    print(f"bundle: {len(bundle)} businesses from {seed_dir}")  # noqa: T201

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        report = await import_seed(session, bundle)
        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    for outcome in report.outcomes:
        print(f"  {outcome.action:8} {outcome.ref}")  # noqa: T201
    print(  # noqa: T201
        f"{'DRY RUN - rolled back' if dry_run else 'imported'}: "
        f"{report.created} created, {report.skipped} skipped"
    )

    if not dry_run and report.event_payloads:
        try:
            for event_type, payload in report.event_payloads:
                await publish("directory", event_type, payload)
            print(f"published {len(report.event_payloads)} search events")  # noqa: T201
        except Exception as exc:  # noqa: BLE001 - rows are committed; index is recoverable
            print(f"(publish failed - run scripts.reindex_search: {exc})")  # noqa: T201
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-dir", type=Path, default=Path("data/seeds/coimbatore"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.seed_dir, dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Verify CLI end-to-end against the dev stack**

Run: `cd backend/core && .venv/Scripts/python.exe -m scripts.import_vendor_seed --dry-run`
Expected: `bundle: 15+ businesses`, outcome lines, `DRY RUN - rolled back`. Then run twice for real:
`.venv/Scripts/python.exe -m scripts.import_vendor_seed` (expect 15+ created) and again (expect 0 created, 15+ skipped).

- [ ] **Step 6: Format, run the whole seed test file, commit**

```bash
cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_seed_import.py -q
git add backend/core/scripts/import_vendor_seed.py backend/core/tests/test_seed_import.py
git commit -m "feat(d27): import_vendor_seed CLI with dry-run + surface proofs"
```

---

### Task 10: compile the 150+ Coimbatore dataset ⚠ HUMAN REVIEW GATE

**Files:**
- Create: `backend/core/data/seeds/coimbatore/raw_coimbatore_sheet.csv` (the authored source, committed — it is PII-free by construction)
- Modify (regenerated by the normalizer): `businesses.csv`, `branches.csv`, `coverage.csv`, `products.csv`

**Interfaces:**
- Consumes: normalizer raw contract incl. Task 4's `description_hi` and Task 5's `ref` merge column; category slugs from Task 1; glossary from Task 6.
- Produces: normalized CSVs with 150+ businesses that Task 15 loads.

- [ ] **Step 1: Author the raw sheet**

Compose `raw_coimbatore_sheet.csv` (columns exactly per the normalizer docstring: `ref,name,type,category_slugs,primary_pincode,description_en,description_ta,description_hi,address,state,district,pincode,lat,lng,coverage_pincodes,vertical_slug,product_name,specs_json,milk_type,fat_percent,pack_size,price_display`). Composition quotas (total ≥150 businesses):

| segment | type | category_slugs | count | notes |
|---|---|---|---|---|
| Brands (Aavin, Hatsun/Arokya, Sakthi, Amul, Heritage, Dodla, Thirumala, Milky Mist) | shop | dairy;shop | 8 | multi-row via shared `ref`: Aavin ~12 parlour branches, Hatsun ~8, others 3–5; 2–4 milk products each; coverage = branch pincodes |
| Milk vendors / private dairies | vendor | dairy | ~55 | 1 branch, 1–2 products, coverage 1–6 nearby pincodes |
| Dairy farms | farm | dairy-farm;dairy | ~25 | 1 branch, usually 1 product |
| Veterinary clinics | shop | veterinarian | ~25 | no products (vertical_slug blank) |
| Cattle-feed suppliers | shop | feed-supplier | ~22 | no products |
| Milk cooperative societies | vendor | cooperative;dairy | ~15 | 1 product where sensible |

Authoring rules (all enforced by the normalizer, so violations surface immediately):
- Real brand names for the brand segment (public knowledge). Other segments: realistic locality-anchored names ("Saibaba Colony Veterinary Clinic", "Ganapathy Cattle Feeds") — plausible local businesses, locality+pincode granularity, NO phone/email anywhere, no lat/lng unless confident (blank is fine — covers() falls back to pincode centroids).
- Pincodes ONLY from `data/geo/pincodes.csv` rows with district LGD 569 (Coimbatore) or the adjacent allowlist (634/587/573/572) — pull the valid list first: spread across ≥25 distinct pincodes; ensure ≥20 businesses cover `641001` (the DoD pincode).
- Every description in en + ta + hi, glossary-consistent (`docs/i18n-glossary.md`), accurate-but-generic, moderation-appropriate. No superlatives that assert unverifiable claims ("best", "certified") — these are unclaimed listings.
- Product specs: `milk_type` from {cow, buffalo, a2, toned, organic}; realistic 2026 Coimbatore prices (₹28–₹60 per 500ml band).

- [ ] **Step 2: Normalize + verify zero rejects**

Run: `cd backend/core && .venv/Scripts/python.exe -m scripts.normalize_vendor_seed data/seeds/coimbatore/raw_coimbatore_sheet.csv --out data/seeds/coimbatore/`
Expected: 150+ businesses written, `rejects.csv` empty or absent. Fix the raw sheet until rejects are zero (never hand-edit the four output CSVs). Then:
`.venv/Scripts/python.exe -m pytest tests/test_vendor_seed.py -q` (contract tests over the shipped CSVs) and
`.venv/Scripts/python.exe -m scripts.import_vendor_seed --dry-run` (expect 150+ validated, no contract errors).

- [ ] **Step 3: HUMAN GATE — present for owner review, WAIT**

Present to the owner (do not proceed until approved): totals per segment/type/category, distinct pincode count, businesses covering 641001, brand branch counts, 10 sample rows (mixed segments) with their ta/hi descriptions, and confirmation that rejects.csv is empty and gitignored. **Stop and wait for explicit approval. If rows are challenged, fix the raw sheet, re-run Step 2, re-present.**

- [ ] **Step 4: Commit (only after approval)**

```bash
git add backend/core/data/seeds/coimbatore/
git commit -m "feat(d27): 150+ Coimbatore vendor/brand seed dataset (owner-reviewed)"
```

---

### Task 11: web-milk locale segment (`[locale]`, as-needed prefix) + switcher

**Files:**
- Create: `apps/web-milk/i18n/routing.ts`, `apps/web-milk/i18n/navigation.ts`, `apps/web-milk/middleware.ts`, `apps/web-milk/app/[locale]/locale-switcher.tsx`
- Modify: `apps/web-milk/i18n/request.ts`, `apps/web-milk/app/[locale]/site-header.tsx`
- Move: everything under `apps/web-milk/app/` EXCEPT `api/`, `sitemap.ts`, `globals.css` into `apps/web-milk/app/[locale]/` (git mv: `page.tsx`, `pincode-hero.tsx`, `layout.tsx`, `site-header.tsx`, `header-location.tsx`, `[pincode]/`, `directory/`, `search/`, `my-needs/`, `post-need/`, `notifications/`)
- Test: build output + root `e2e/milk-home.spec.ts` + `e2e/vendor-profile.spec.ts` (URLs unchanged for en — they must pass unmodified)

**Interfaces:**
- Produces: `routing` (locales en/ta/hi, defaultLocale en, `localePrefix: "as-needed"`), `Link/useRouter/usePathname/redirect` from `@/i18n/navigation` — Tasks 12–14 import these. `/` stays static English; `/ta/...`, `/hi/...` statically generated.

- [ ] **Step 1: Routing + navigation + middleware + request config**

`i18n/routing.ts`:

```ts
import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "ta", "hi"],
  defaultLocale: "en",
  // "/" stays the canonical English URL (Lighthouse audits it; D23 static
  // fix must hold). ta/hi live under /ta /hi with hreflang alternates.
  localePrefix: "as-needed",
});
```

`i18n/navigation.ts`:

```ts
import { createNavigation } from "next-intl/navigation";

import { routing } from "./routing";

export const { Link, redirect, usePathname, useRouter } = createNavigation(routing);
```

`middleware.ts` (app root, beside `next.config.ts`):

```ts
import createMiddleware from "next-intl/middleware";

import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  // Skip API/BFF proxies, Next internals and any file with an extension
  // (sitemap.xml, favicon, images). Everything else gets locale handling.
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
```

`i18n/request.ts` (replace the pinned-en config; the static-rendering guarantee now comes from `setRequestLocale`, not from avoiding `requestLocale` — update the comment accordingly):

```ts
import { getUiMessages } from "@agri/ui/i18n";
import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";

import { routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested) ? requested : routing.defaultLocale;
  return { locale, messages: getUiMessages(locale) };
});
```

- [ ] **Step 2: Move the route tree**

`git mv` the files/dirs listed above into `app/[locale]/`. Then:
- New minimal `app/layout.tsx` (root passthrough — keep the `globals.css` import and any font/Sentry setup here if the old layout had it; `<html>`/`<body>` move to the locale layout):

```tsx
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
```

- `app/[locale]/layout.tsx`: adapt the moved layout — it now receives `params: Promise<{ locale: string }>`; add:

```tsx
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { routing } from "@/i18n/routing";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

// inside the default export, before rendering:
const { locale } = await params;
if (!hasLocale(routing.locales, locale)) notFound();
setRequestLocale(locale);
// keep the existing provider/body structure; <html lang={locale}>
```

- EVERY page under `[locale]` that renders statically/ISR (`page.tsx`, `[pincode]/page.tsx`, `directory/businesses/[slug]/page.tsx`, `search`, `my-needs`, `post-need`, `notifications`) awaits its `params` for `locale` and calls `setRequestLocale(locale)` FIRST (before any `getTranslations`). Dynamic params types change from `Promise<{ pincode: string }>` to `Promise<{ locale: string; pincode: string }>` etc. — update each signature and `generateMetadata`.
- Swap internal navigation to the locale-aware module: `grep -rn "next/link" apps/web-milk/app` — every internal `<Link>`/`useRouter`/`usePathname` in moved files switches to `@/i18n/navigation` imports (external links and the api-proxy fetches stay untouched). Plain `<a href={`/${pincode}`}>` in `[pincode]/page.tsx` becomes the navigation `Link`.
- `@/` import alias: confirm tsconfig paths cover `i18n/*` (mirror how `@/lib/*` resolves).

- [ ] **Step 3: Locale switcher in the header**

`app/[locale]/locale-switcher.tsx`:

```tsx
"use client";

import { useLocale, useTranslations } from "next-intl";

import { Link, usePathname } from "@/i18n/navigation";

const LABELS = { en: "EN", ta: "த", hi: "हिं" } as const;

export function LocaleSwitcher() {
  const pathname = usePathname();
  const active = useLocale();
  const t = useTranslations("ui.localeSwitcher");
  return (
    <nav aria-label={t("label")} className="flex items-center gap-0.5">
      {(Object.keys(LABELS) as Array<keyof typeof LABELS>).map((locale) => (
        <Link
          key={locale}
          href={pathname}
          locale={locale}
          prefetch={false}
          aria-current={locale === active ? "true" : undefined}
          className={`flex min-h-11 min-w-11 items-center justify-center rounded-card px-1.5 text-[12.5px] font-bold no-underline ${
            locale === active ? "bg-brand-soft text-brand-deep" : "text-sub"
          }`}
        >
          {LABELS[locale]}
        </Link>
      ))}
    </nav>
  );
}
```

(Token classes shown follow the existing header components — verify against `docs/design-system.md` and reuse the exact token names the site-header already uses; ≥44px tap targets via `min-h-11 min-w-11`.) Add `<LocaleSwitcher />` to `site-header.tsx`'s `right` cluster, first in the fragment.

- [ ] **Step 4: hreflang on the home page**

In `app/[locale]/page.tsx`'s `generateMetadata`, extend the returned metadata:

```ts
alternates: {
  canonical: "https://milk.in/",
  languages: {
    en: "https://milk.in/",
    ta: "https://milk.in/ta",
    hi: "https://milk.in/hi",
    "x-default": "https://milk.in/",
  },
},
```

(Merge with whatever `buildMetadata` already returns — spread its result and override `alternates`.)

- [ ] **Step 5: Verify static rendering + e2e**

Run: `pnpm --filter @agri/web-milk typecheck && pnpm --filter @agri/web-milk lint && pnpm --filter @agri/web-milk build`
Expected: build succeeds; the route table shows `/[locale]` as `● (SSG)` with `/`, `/ta`, `/hi` prerendered — NOT `ƒ`. If home went dynamic, a page is missing `setRequestLocale` — fix before proceeding.
Then with the dev stack up: `pnpm exec playwright test milk-home vendor-profile --config e2e/playwright.config.ts`
Expected: PASS unmodified (en URLs unchanged). Manually spot-check `http://localhost:3000/ta` renders Tamil.

- [ ] **Step 6: Commit**

```bash
git add apps/web-milk
git commit -m "feat(d27): web-milk locale segment (en/ta/hi) with static rendering preserved"
```

---

### Task 12: `/c/[category]` landing pages

**Files:**
- Create: `apps/web-milk/lib/categories.ts`, `apps/web-milk/app/[locale]/c/[category]/page.tsx`
- Modify: `apps/web-milk/app/[locale]/pincode-hero.tsx` (optional href-builder prop)
- Test: build output + manual render

**Interfaces:**
- Consumes: `ui.dairyCategories.*` messages (Task 6), routing/navigation (Task 11).
- Produces: `DAIRY_CATEGORIES` + `CATEGORY_MESSAGE_KEY` in `lib/categories.ts` — Task 13's browse and Task 14's chips import these.

- [ ] **Step 1: Category constants**

`apps/web-milk/lib/categories.ts`:

```ts
/** D27 dairy service categories — slugs mirror alembic 0026 exactly. */
export const DAIRY_CATEGORIES = [
  "veterinarian",
  "feed-supplier",
  "dairy-farm",
  "cooperative",
] as const;

export type DairyCategory = (typeof DAIRY_CATEGORIES)[number];

/** JSON message keys can't contain "-": slug → ui.dairyCategories key. */
export const CATEGORY_MESSAGE_KEY: Record<DairyCategory, string> = {
  veterinarian: "veterinarian",
  "feed-supplier": "feedSupplier",
  "dairy-farm": "dairyFarm",
  cooperative: "cooperative",
};

export function isDairyCategory(value: string): value is DairyCategory {
  return (DAIRY_CATEGORIES as readonly string[]).includes(value);
}
```

- [ ] **Step 2: Extend PincodeHero**

Add an optional prop to `pincode-hero.tsx` so the landing can route into category browse — default preserves current behavior exactly:

```ts
// prop: hrefForPincode?: (pincode: string) => string   (default: (p) => `/${p}`)
```

Apply it where the component currently builds its navigation target (read the file; it routes to `/${pincode}` on submit — call the prop instead).

- [ ] **Step 3: The landing page**

`app/[locale]/c/[category]/page.tsx`:

```tsx
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { CATEGORY_MESSAGE_KEY, DAIRY_CATEGORIES, isDairyCategory } from "@/lib/categories";
import { routing } from "@/i18n/routing";

import { PincodeHero } from "../../pincode-hero";

const SITE = "https://milk.in";

export const revalidate = 3600;

export function generateStaticParams() {
  return routing.locales.flatMap((locale) =>
    DAIRY_CATEGORIES.map((category) => ({ locale, category })),
  );
}

type Params = Promise<{ locale: string; category: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale, category } = await params;
  if (!isDairyCategory(category)) return { title: "Milk.in" };
  const t = await getTranslations({
    locale,
    namespace: `ui.dairyCategories.${CATEGORY_MESSAGE_KEY[category]}`,
  });
  return buildMetadata({
    title: `${t("name")} — Milk.in`,
    description: t("description"),
    canonical: canonicalUrl(SITE, `/c/${category}`),
    siteName: "Milk.in",
  });
}

function collectionJsonLd(name: string, description: string, canonical: string): string {
  return JSON.stringify({
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name,
    description,
    url: canonical,
  }).replaceAll("<", "\\u003c");
}

export default async function CategoryLandingPage({ params }: { params: Params }) {
  const { locale, category } = await params;
  if (!isDairyCategory(category)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations(`ui.dairyCategories.${CATEGORY_MESSAGE_KEY[category]}`);
  const canonical = canonicalUrl(SITE, `/c/${category}`);
  return (
    <main className="mx-auto flex w-full max-w-[720px] flex-col gap-5 px-4 py-8">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: collectionJsonLd(t("name"), t("description"), canonical),
        }}
      />
      <h1 className="font-display text-[26px] font-extrabold text-ink">{t("name")}</h1>
      <p className="text-[15px] text-sub">{t("description")}</p>
      <PincodeHero hrefForPincode={(pincode) => `/${pincode}?category=${category}`} />
    </main>
  );
}
```

(Adapt the `PincodeHero` import path/props to the real component — read it first; if it needs strings props, pass the localized ones the home page passes.)

- [ ] **Step 4: Verify + commit**

Run: `pnpm --filter @agri/web-milk typecheck && pnpm --filter @agri/web-milk lint && pnpm --filter @agri/web-milk build`
Expected: `/c/[category]` prerendered for 4 categories × 3 locales. Manually load `/c/veterinarian` and `/ta/c/veterinarian`.

```bash
git add apps/web-milk
git commit -m "feat(d27): dairy category landing pages"
```

---

### Task 13: category browse on `/[pincode]`

**Files:**
- Create: `apps/web-milk/lib/directory.ts` (covers fetch), `apps/web-milk/app/[locale]/[pincode]/category-results.tsx`, `apps/web-milk/app/[locale]/[pincode]/category-chips.tsx`
- Modify: `apps/web-milk/app/[locale]/[pincode]/page.tsx`
- Test: build + manual + existing e2e stays green

**Interfaces:**
- Consumes: `GET /directory/covers/{pincode}?category=` (Task 2), `lib/categories.ts` (Task 12), `ui.categoryBrowse` messages (Task 6).
- Produces: `/{pincode}?category=<slug>` browse views.

- [ ] **Step 1: The covers fetch**

`apps/web-milk/lib/directory.ts` — mirror `lib/milk.ts`'s server-fetch style exactly (same API base env var, same error handling that returns `null` on non-ok):

```ts
export type CoversItem = {
  id: string;
  name: string;
  slug: string;
  type: string;
  verification_status: string;
  subscription_tier: string;
  primary_pincode: string;
  distance_m: number;
  lat: string | null;
  lng: string | null;
};

export async function fetchCovers(
  pincode: string,
  category: string,
): Promise<{ items: CoversItem[]; next_cursor: string | null } | null> {
  // same base + revalidate options as fetchMilkHome; path:
  // `/directory/covers/${pincode}?category=${category}`
}
```

- [ ] **Step 2: Wire the page**

In `[locale]/[pincode]/page.tsx`:
- `searchParams` type gains `category?: string`.
- After pincode validation: `const { type = "all", category } = await searchParams;`
- When `category` is set and `isDairyCategory(category)`: fetch `fetchCovers(pincode, category)`; render the category view INSTEAD of the milk blend: localized heading via `t("ui.categoryBrowse.heading", {category: <localized name>, place})`, `<CategoryChips pincode={pincode} active={category} />`, then `<CategoryResults items={...} />` (Cards linking to `/directory/businesses/${slug}` via the navigation `Link`, showing name, localized category/type line, `distance_m` rendered as `t("ui.brandPage.kmAway", {km: (distance_m / 1000).toFixed(1)})` when < the unlocatable sentinel). Empty list → `t("ui.categoryBrowse.empty")`.
- Category views set `robots: { index: false, follow: true }` in `generateMetadata` when `category` present (canonical stays `/{pincode}`) — thin query-param variants must not compete with the landing pages.
- When `category` is absent: existing milk view untouched; add `<CategoryChips pincode={pincode} active={null} />` under the `TypeFilterRow` so the four dairy categories are discoverable from every covered pincode page.
- `CategoryChips`: navigation `Link`s to `/${pincode}?category=${slug}` for each of `DAIRY_CATEGORIES` + an "all milk" chip to `/${pincode}`; active chip styled like `TypeFilterRow`'s active state (reuse its exact classes); ≥44px tap targets.

- [ ] **Step 3: Verify + commit**

Run: typecheck + lint + build; then with dev stack + Task 9's starter seed loaded, load `/641001?category=veterinarian` — expect the seeded vet clinic (from starter sample after Task 10 regen; before that, whatever test rows exist — verify shape, not counts). Existing `e2e/milk-home.spec.ts` must stay green (the default milk view is unchanged).

```bash
git add apps/web-milk
git commit -m "feat(d27): covers-based category browse on pincode pages"
```

---

### Task 14: brand variant + NearbyShops + category chips on the business page

**Files:**
- Create: `apps/web-milk/app/[locale]/directory/businesses/[slug]/nearby-shops.tsx`
- Modify: `apps/web-milk/app/[locale]/directory/businesses/[slug]/page.tsx`, `apps/web-milk/lib/business.ts`
- Test: build + `e2e/vendor-profile.spec.ts` green + manual brand-page check

**Interfaces:**
- Consumes: `GET /api/directory/businesses/{slug}/nearby-branches?pincode=` (Task 3 via the existing web-milk directory proxy), `ui.brandPage` messages, `lib/categories.ts`.
- Produces: brand layout when `business.type === "shop" && products.length > 0`.

- [ ] **Step 1: Types**

In `lib/business.ts`: confirm `BusinessDetail` already carries `categories` (the backend detail response includes it — router.py:470); if the type omits it, add `categories: Array<{ slug: string; name: Record<string, string> }>` matching the wire shape. Add:

```ts
export type NearbyBranch = {
  id: string;
  address: string;
  district: string;
  state: string;
  pincode: string;
  lat: string | null;
  lng: string | null;
  distance_m: number;
};
```

- [ ] **Step 2: NearbyShops client component**

`nearby-shops.tsx` — follow `reveal-contact.tsx`'s client-component conventions (fetch via the same `/api/directory` proxy base, same error copy patterns):

```tsx
"use client";

import { Card } from "@agri/ui";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import type { NearbyBranch } from "@/lib/business";

const PIN_RE = /^\d{6}$/;

export function NearbyShops({ slug, initialPincode }: { slug: string; initialPincode: string }) {
  const t = useTranslations("ui.brandPage");
  const [pincode, setPincode] = useState(initialPincode);
  const [items, setItems] = useState<NearbyBranch[] | null>(null);
  const [busy, setBusy] = useState(false);

  const search = useCallback(async (pin: string) => {
    if (!PIN_RE.test(pin)) return;
    setBusy(true);
    try {
      const response = await fetch(
        `/api/directory/businesses/${slug}/nearby-branches?pincode=${pin}`,
      );
      setItems(response.ok ? (await response.json()).items : []);
    } catch {
      setItems([]);
    } finally {
      setBusy(false);
    }
  }, [slug]);

  useEffect(() => {
    void search(initialPincode);
  }, [initialPincode, search]);

  return (
    <section className="space-y-2.5" aria-labelledby="nearby-shops-h">
      <h2 id="nearby-shops-h" className="font-display text-[16px] font-extrabold text-ink">
        {t("shopsNearYou")}
      </h2>
      <form
        className="flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void search(pincode);
        }}
      >
        <label className="flex flex-col gap-1 text-[12.5px] font-semibold text-sub">
          {t("pincodeLabel")}
          <input
            value={pincode}
            onChange={(event) => setPincode(event.target.value.replace(/\D/g, "").slice(0, 6))}
            inputMode="numeric"
            pattern="\d{6}"
            className="h-11 w-28 rounded-card border border-line bg-card px-3 text-[15px] text-ink"
          />
        </label>
        <button
          type="submit"
          disabled={busy || !PIN_RE.test(pincode)}
          className="h-11 rounded-card bg-brand-deep px-4 text-[13.5px] font-bold text-white disabled:opacity-50"
        >
          {t("find")}
        </button>
      </form>
      {items && items.length === 0 ? (
        <p className="text-[13px] text-sub">{t("empty", { pincode })}</p>
      ) : null}
      <ul className="space-y-2">
        {(items ?? []).map((branch) => (
          <li key={branch.id}>
            <Card className="space-y-1 p-3">
              <p className="text-[13.5px] font-semibold text-ink">{branch.address}</p>
              <p className="text-[12.5px] text-sub">
                {branch.district}, {branch.state} {branch.pincode}
                {branch.distance_m < 1_000_000_000
                  ? ` · ${t("kmAway", { km: (branch.distance_m / 1000).toFixed(1) })}`
                  : ""}
              </p>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

(Verify button/input classes against the design system + existing forms — reuse `lead-form.tsx`'s field styling verbatim rather than inventing new classes; keep `text-white` only if the design system's button uses it, else its token.)

- [ ] **Step 3: Brand variant + chips in the page**

In `[slug]/page.tsx`:
- `const isBrand = business.type === "shop" && products.length > 0;`
- When `isBrand`: JSON-LD `@type` becomes `["Organization", "Brand"]` (same fields otherwise — adjust `businessJsonLd` to take an `isBrand` flag); the products section heading uses `t("ui.brandPage.products")`; render `<NearbyShops slug={business.slug} initialPincode={business.primary_pincode} />` between products and the coverage section. Vendor pages (`!isBrand`) are byte-identical to today.
- Category chips (ALL businesses): after the header, for each of the business's `categories` whose slug `isDairyCategory`, render a navigation `Link` chip to `/c/${slug}` (label = localized name via `ui.dairyCategories.*`); non-dairy category slugs render as plain `Badge`s. This is spec Part D (cross-links) — dairy service categories reachable from vendor pages.

- [ ] **Step 4: Verify + commit**

Run: typecheck + lint + build; `pnpm exec playwright test vendor-profile --config e2e/playwright.config.ts` (vendor pages unchanged ⇒ green). Manually load a seeded brand page (e.g. Aavin after Task 10, or `make_business.py --type shop` before) — products grid + shops-near-you renders, pincode edit refetches.

```bash
git add apps/web-milk
git commit -m "feat(d27): brand page variant with shops-near-you + category cross-links"
```

---

### Task 15: real load, end-to-end verification, full gates, PR

**Files:**
- No new source files. Runs tools; may touch docs.

**Interfaces:**
- Consumes: everything above. Produces the PR.

- [ ] **Step 1: Load the reviewed seed into the dev DB**

Dev stack up (postgres 55432 / redis / meili / search worker running). Then:

```bash
cd backend/core
.venv/Scripts/python.exe -m scripts.import_vendor_seed --dry-run   # expect 150+ validated
.venv/Scripts/python.exe -m scripts.import_vendor_seed             # expect 150+ created
.venv/Scripts/python.exe -m scripts.import_vendor_seed             # expect 0 created (idempotency proof)
```

- [ ] **Step 2: Verify all four DoD surfaces against the live stack**

1. `curl "http://localhost:8000/directory/covers/641001?limit=5"` → seeded names present; `?category=veterinarian` → vets only.
2. `curl "http://localhost:8000/search?q=aavin&site=milk"` (adapt to the real search route shape) → seeded brand doc present. If missing, the worker wasn't consuming — check worker logs, or run `.venv/Scripts/python.exe -m scripts.reindex_search`, and note which happened in the PR description.
3. Brand accuracy: `curl "http://localhost:8000/directory/businesses/<aavin-slug>/nearby-branches?pincode=641001"` → branches sorted by distance.
4. Frontend walk: `/` (en, static), `/ta` (Tamil), `/c/dairy-farm`, `/641001?category=cooperative`, one brand page, one vendor page.

- [ ] **Step 3: Full local CI gates (all must pass BEFORE push — known trap: don't discover mypy/import-linter failures in CI)**

```bash
cd backend/core
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe -m ruff format --check . && .venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy .
.venv/Scripts/python.exe -m lint_imports  # or the repo's lint-imports invocation — match CI's workflow file
.venv/Scripts/python.exe scripts/dump_public_routes.py --check
cd ../..
pnpm --filter @agri/ui test
pnpm exec turbo run build typecheck lint --filter=@agri/web-milk --filter=@agri/ui
node scripts/lhci-affected.mjs   # web-milk home must clear the 0.90 floor
pnpm exec playwright test --config e2e/playwright.config.ts
```

Fix anything red. For Lighthouse: if web-milk home dropped below 0.90, the locale change broke static rendering — check the build route table for `ƒ` pages and missing `setRequestLocale` calls; do NOT re-baseline thresholds.

- [ ] **Step 4: Push + PR**

```bash
git push -u origin feat/d27-dairy-directory
```

Open the PR to `dev` titled `feat(d27): dairy directory + seed` (PR-title check runs conventional-commit lint; a title fix requires re-running the check — known trap). Use the same PR-creation path as D18/D24 (GitHub API with the stored credential — `gh` CLI is not installed). PR body: summary per spec part (A–D), the four non-negotiables each with the test/command that proves it, the owner-review note for the dataset, and the standard footer:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

---

## Self-Review Notes (already applied)

- Spec coverage: Part A → Tasks 1, 2, 12, 13 · Part B → Tasks 3, 14 · Part C seed → Tasks 4, 5, 7, 8, 9, 10, 15 · Part C′ TA/HI → Tasks 6, 11 · Part D → Task 14 Step 3 · NN#1 → Tasks 9, 15 · NN#2 → Task 6 · NN#3 → Tasks 3, 14 · NN#4 → Tasks 8, 15.
- Deliberately out of scope (per spec): no new engine/module/type-enum value, no D63 pipeline, no nationwide rows, no billing/premium changes, no VPS/staging work (owner-gated).
- Known-trap ledger honored: per-task ruff format (D16), parallel-pytest DB (D19), e2e login/hydration traps untouched (D25 specs unmodified), Lighthouse local floor (D23), public_routes.txt same-commit rule, rejects.csv never committed, no gh CLI.
