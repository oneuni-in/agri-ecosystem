# D24 Vendor Profiles + Tracked Contact + Map — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Milk-vertical vendor profile pages (SSR, LocalBusiness JSON-LD) with D18-tracked Call/WhatsApp reveal + lead attribution, and a lazy MapLibre map synced with the distance-sorted vendor list on `/{pincode}`.

**Architecture:** Backend gets three additive changes (covers() returns nearest-branch lat/lng, the reveal route records a deduped `contact` inquiry for attribution, public business detail exposes coverage pincodes). All frontend work lands in `apps/web-milk`: a new `/directory/businesses/[slug]` ISR page reusing web-agri's proven reveal/lead/review components via new BFF proxies, and a client-island map on the pincode page. No new public API routes, no new caps, no schema migrations.

**Tech Stack:** FastAPI + SQLAlchemy async + pytest (backend/core, host Python 3.12 venv at `backend/core/.venv`), Next.js 15 App Router + Tailwind 3 tokens (`apps/web-milk`), `maplibre-gl` (new dep, web-milk only), Playwright (`e2e/`).

## Global Constraints

- Work on branch `feat/d24-vendor-profiles` (already created from dev). NEVER commit to dev or main. PR targets dev, title `feat(d24): vendor profiles`.
- Conventional commits. End commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Design system: tokens only — NO raw hex colors in app code (`pnpm check:hex` gate). Buttons ≥44px tap targets.
- Backend: never log request bodies/query strings/phone numbers; `public_routes.txt` must NOT change (no new public routes in this package); OFFSET pagination is test-banned; IDs are UUIDv7.
- After each backend task: run `ruff format` on touched files BEFORE committing (D16 lesson: CI fails un-formatted code).
- MapLibre only — no Google Maps JS.
- Backend commands run from `d:\agri-ecosystem\backend\core` using `.venv/Scripts/python.exe`. Frontend commands run from repo root `d:\agri-ecosystem`. Backend tests need the dev docker services up (postgres + redis — `docker compose up -d` at repo root if not running).
- Reviews stay moderation-pending by default; contact reveal cap/log semantics must not change.

---

### Task 1: covers() returns nearest-branch coordinates

**Files:**
- Modify: `backend/core/modules/directory/covers.py`
- Test: `backend/core/tests/test_directory_covers.py`

**Interfaces:**
- Consumes: existing `covers()` SQL/dataclasses.
- Produces: `CoversItem` gains `lat: Decimal | None`, `lng: Decimal | None` (coords of the business's nearest geocoded branch; `None` when the business has no geocoded branch). `CoversItemOut` (Task 1 also updates it, see step 3) mirrors them. Task 2 consumes `item.lat`/`item.lng`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/core/tests/test_directory_covers.py` (imports `service`, `covers`, `Decimal`, `uuid` already present at top of file):

```python
async def test_covers_returns_nearest_branch_coords(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _covered_business(db_session, "Near", branch_at=(10.9232, 76.9686))
    await _covered_business(db_session, "Branchless", primary="600001")  # centroid fallback
    page = await covers(db_session, pincode="641001")
    near, branchless = page.items
    assert near.name == "Near"
    assert near.lat is not None and near.lng is not None
    assert float(near.lat) == pytest.approx(10.9232, abs=1e-4)
    assert float(near.lng) == pytest.approx(76.9686, abs=1e-4)
    # centroid-fallback businesses are list-only: distance yes, coords no
    assert branchless.distance_m > 300_000
    assert branchless.lat is None and branchless.lng is None


async def test_covers_picks_coords_of_nearest_branch(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    owner = uuid.uuid4()
    business = await service.create_business(
        db_session, owner_user_id=owner, name="TwoBranch", type_="vendor",
        primary_pincode="641001",
    )
    await service.set_coverage(
        db_session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    for lat in ("11.2832", "10.9232"):  # far (~40km) first, near (~0km) second
        await service.add_branch(
            db_session, owner_user_id=owner, business_id=business.id,
            address="1 Main Rd", state="Tamil Nadu", district="Coimbatore",
            pincode="641001", lat=Decimal(lat), lng=Decimal("76.9686"),
        )
    page = await covers(db_session, pincode="641001")
    assert page.items[0].name == "TwoBranch"
    assert float(page.items[0].lat) == pytest.approx(10.9232, abs=1e-4)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd d:\agri-ecosystem\backend\core
.venv/Scripts/python.exe -m pytest tests/test_directory_covers.py -q
```
Expected: the two new tests FAIL with `TypeError: CoversItem.__init__() got an unexpected keyword argument 'lat'` or `AttributeError: 'CoversItem' object has no attribute 'lat'`; all pre-existing tests still pass.

- [ ] **Step 3: Implement**

In `backend/core/modules/directory/covers.py`:

(a) Add to imports: `from decimal import Decimal`

(b) Extend the dataclass:

```python
@dataclass(frozen=True, slots=True)
class CoversItem:
    id: uuid.UUID
    name: str
    slug: str
    type: str
    verification_status: str
    subscription_tier: str
    primary_pincode: str
    distance_m: int
    lat: Decimal | None
    lng: Decimal | None
```

(c) In `_BASE_SQL`, change the SELECT list to end with `d.distance_m, nb.lat, nb.lng` and add a second lateral AFTER the existing `) d` block and BEFORE the `WHERE` clause (the existing distance lateral is untouched — same rounding, same fallback chain):

```python
_BASE_SQL = f"""
WITH q AS (
    SELECT centroid_lat AS lat, centroid_lon AS lon
    FROM geo.pincodes WHERE pincode = :pincode
)
SELECT b.id, b.name, b.slug, b.type, b.verification_status,
       b.subscription_tier, b.primary_pincode, d.distance_m, nb.lat, nb.lng
FROM directory.businesses b
JOIN directory.business_coverage c
  ON c.business_id = b.id AND c.pincode = :pincode
CROSS JOIN q
CROSS JOIN LATERAL (
    SELECT CAST(ROUND(COALESCE(
        (SELECT MIN({_BRANCH_DISTANCE}) FROM directory.branches br
         WHERE br.business_id = b.id
           AND br.lat IS NOT NULL AND br.lng IS NOT NULL
           AND br.deleted_at IS NULL),
        (SELECT {_PRIMARY_DISTANCE} FROM geo.pincodes p
         WHERE p.pincode = b.primary_pincode),
        {UNLOCATABLE_M}
    )) AS BIGINT) AS distance_m
) d
LEFT JOIN LATERAL (
    SELECT br.lat, br.lng
    FROM directory.branches br
    WHERE br.business_id = b.id
      AND br.lat IS NOT NULL AND br.lng IS NOT NULL
      AND br.deleted_at IS NULL
    ORDER BY {_BRANCH_DISTANCE}
    LIMIT 1
) nb ON TRUE
WHERE b.status = 'active' AND b.deleted_at IS NULL
"""
```

(d) In the `covers()` item construction, add `lat=m["lat"], lng=m["lng"],` after `distance_m=...`.

(e) In `backend/core/modules/directory/schemas.py`, extend `CoversItemOut` (router builds it via `CoversItemOut(**asdict(item))`, so field names must match exactly):

```python
class CoversItemOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    type: str
    verification_status: str
    subscription_tier: str
    primary_pincode: str
    distance_m: int
    lat: Decimal | None
    lng: Decimal | None
```
(`Decimal` is already imported in schemas.py.)

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/Scripts/python.exe -m pytest tests/test_directory_covers.py tests/test_directory_router.py -q
```
Expected: ALL PASS (router test included because `covers_search` serializes the new fields).

- [ ] **Step 5: Format and commit**

```
.venv/Scripts/python.exe -m ruff format modules/directory/covers.py modules/directory/schemas.py tests/test_directory_covers.py
.venv/Scripts/python.exe -m ruff check modules/directory/covers.py modules/directory/schemas.py tests/test_directory_covers.py
git add -A
git commit -m "feat(d24): covers() returns nearest-branch lat/lng for map pins"
```

---

### Task 2: Propagate lat/lng onto milk-home cards

**Files:**
- Modify: `backend/core/modules/directory/milk_home.py`
- Modify: `backend/core/modules/directory/milk_home_schemas.py`
- Test: `backend/core/tests/test_milk_home.py`

**Interfaces:**
- Consumes: `CoversItem.lat` / `CoversItem.lng` from Task 1.
- Produces: `MilkCard` dataclass gains `lat: Decimal | None`, `lng: Decimal | None`; wire schema `MilkCardOut` gains `lat: float | None`, `lng: float | None`. Task 9's `lib/milk.ts` mirrors these as `lat: number | null; lng: number | null`.

- [ ] **Step 1: Write the failing test**

`test_milk_home.py` has async tests using `db_session` + `tn_geo_sample` and seeds via `service`/`catalog_service` (see `test_milk_home_covered_*` tests further down the file for the seeding helper it uses — reuse whatever helper seeds a covered vendor; if the existing covered-scope test seeds inline, copy that seeding block). Add:

```python
@pytest.mark.asyncio
async def test_milk_home_cards_carry_branch_coords(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    owner = uuid.uuid4()
    business = await service.create_business(
        db_session, owner_user_id=owner, name="Geo Dairy", type_="vendor",
        primary_pincode="641001",
    )
    await service.set_coverage(
        db_session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    await service.add_branch(
        db_session, owner_user_id=owner, business_id=business.id,
        address="1 Main Rd", state="Tamil Nadu", district="Coimbatore",
        pincode="641001", lat=Decimal("10.923220"), lng=Decimal("76.968600"),
    )
    product = await catalog_service.create_product(
        db_session, owner_user_id=owner, business_id=business.id,
        vertical_slug="milk", name="Cow Milk",
        specs={"milk_type": "cow", "fat_percent": 4.0, "pack_size": "1l"},
        price_display="₹55/L",
    )
    await catalog_service.moderate_product(db_session, product_id=product.id, approve=True)

    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, cursor=None, limit=20
    )
    assert result.scope == "covered"
    card = result.vendors[0]
    assert card.lat is not None and float(card.lat) == pytest.approx(10.92322, abs=1e-4)
    assert card.lng is not None and float(card.lng) == pytest.approx(76.9686, abs=1e-4)
```

(If `catalog_service.moderate_product`'s signature differs in this file's existing usage, mirror the existing call — `seed_e2e_milk.py` uses `moderate_product(session, product_id=..., approve=True)`.)

- [ ] **Step 2: Run test to verify it fails**

```
.venv/Scripts/python.exe -m pytest tests/test_milk_home.py -q
```
Expected: new test FAILS (`MilkCard` has no `lat`); existing tests pass.

- [ ] **Step 3: Implement**

In `milk_home.py`: add `from decimal import Decimal` to imports; extend the dataclass and constructor call:

```python
@dataclass(frozen=True, slots=True)
class MilkCard:
    id: uuid.UUID
    name: str
    slug: str
    type: str
    verification_status: str
    subscription_tier: str
    distance_m: int
    lat: Decimal | None
    lng: Decimal | None
    products: list[Product]
```

and in the card construction inside `milk_home()` add `lat=item.lat, lng=item.lng,` after `distance_m=item.distance_m,`.

In `milk_home_schemas.py`, extend `MilkCardOut` with `lat: float | None` and `lng: float | None` (after `distance_m`), and in `_card_out()` add:

```python
        lat=float(card.lat) if card.lat is not None else None,
        lng=float(card.lng) if card.lng is not None else None,
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/Scripts/python.exe -m pytest tests/test_milk_home.py tests/test_catalog_router.py -q
```
Expected: ALL PASS.

- [ ] **Step 5: Format and commit**

```
.venv/Scripts/python.exe -m ruff format modules/directory/milk_home.py modules/directory/milk_home_schemas.py tests/test_milk_home.py
git add -A
git commit -m "feat(d24): milk-home cards carry nearest-branch coords"
```

---

### Task 3: Public business detail exposes coverage pincodes

**Files:**
- Modify: `backend/core/modules/directory/schemas.py` (`BusinessDetailOut`)
- Modify: `backend/core/modules/directory/router.py` (`get_business_detail`)
- Test: `backend/core/tests/test_directory_router.py`

**Interfaces:**
- Produces: `BusinessDetailOut.coverage_pincodes: list[str]` (sorted ascending). Task 6's `lib/business.ts` mirrors it.

- [ ] **Step 1: Write the failing test**

In `test_directory_router.py`, extend `test_public_detail_by_slug` — after the existing assertions on `body`, seed coverage and re-fetch. Replace the test with:

```python
async def test_public_detail_by_slug(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _ = api
    created = await http.post("/directory/businesses", json=CREATE_BODY, headers=_as(USER_A))
    slug = created.json()["slug"]
    business_id = created.json()["id"]
    detail = await http.get(f"/directory/businesses/{slug}")  # public: NO auth header
    assert detail.status_code == 200
    body = detail.json()
    assert body["business"]["name"] == "Anbu Milk Farm"
    assert body["branches"] == []
    assert body["categories"] == []
    assert body["coverage_pincodes"] == []
    # coverage pincodes are public, non-PII profile content (D24.A)
    await http.put(
        f"/directory/businesses/{business_id}/coverage",
        json={"pincodes": ["641002", "641001"]},
        headers=_as(USER_A),
    )
    covered = await http.get(f"/directory/businesses/{slug}")
    assert covered.json()["coverage_pincodes"] == ["641001", "641002"]  # sorted
    assert (await http.get("/directory/businesses/no-such-slug")).status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv/Scripts/python.exe -m pytest tests/test_directory_router.py::test_public_detail_by_slug -q
```
Expected: FAIL with `KeyError: 'coverage_pincodes'`.

- [ ] **Step 3: Implement**

`schemas.py`:

```python
class BusinessDetailOut(BaseModel):
    business: BusinessOut
    branches: list[PublicBranchOut]
    categories: list[CategoryOut]
    coverage_pincodes: list[str]
```

`router.py` — add `BusinessCoverage` to the `from modules.directory.models import ...` line, then in `get_business_detail`:

```python
@router.get("/businesses/{slug}", public=True)
async def get_business_detail(slug: str, session: SessionDep) -> BusinessDetailOut:
    """Public business profile (SSR source). Suspended/deleted -> 404; renamed
    slugs 301 via SlugRedirectMiddleware reading slug_redirects."""
    result = await service.get_by_slug(session, slug)
    if result is None:
        raise HTTPException(status_code=404, detail="Business not found")
    business, branches, categories = result
    pincodes = (
        await session.scalars(
            select(BusinessCoverage.pincode)
            .where(BusinessCoverage.business_id == business.id)
            .order_by(BusinessCoverage.pincode)
        )
    ).all()
    return BusinessDetailOut(
        business=_business_out(business),
        branches=[_public_branch_out(b) for b in branches],
        categories=[_category_out(c) for c in categories],
        coverage_pincodes=list(pincodes),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/Scripts/python.exe -m pytest tests/test_directory_router.py tests/test_contact_reveal.py -q
```
Expected: ALL PASS.

- [ ] **Step 5: Format and commit**

```
.venv/Scripts/python.exe -m ruff format modules/directory/router.py modules/directory/schemas.py tests/test_directory_router.py
git add -A
git commit -m "feat(d24): expose coverage pincodes on public business detail"
```

---

### Task 4: Reveal records a deduped contact-inquiry (attribution)

**Files:**
- Modify: `backend/core/modules/directory/leads_service.py`
- Modify: `backend/core/modules/directory/router.py` (`reveal_branch_contact`)
- Test: `backend/core/tests/test_contact_reveal.py`

**Interfaces:**
- Consumes: `Inquiry` model, `_publish_best_effort` pattern, existing reveal handler.
- Produces: `leads_service.record_reveal_inquiry(session, *, user_id: uuid.UUID, business_id: uuid.UUID, pincode: str) -> Inquiry | None` — returns `None` when the same user already has a reveal-sourced contact inquiry for this business today (UTC). Reveal handler emits `lead.created` when an inquiry was created and the business has an owner. D18 invariants unchanged: cap → ContactReveal row → numbers; no phone in logs.

- [ ] **Step 1: Write the failing tests**

Append to `test_contact_reveal.py` (add `from modules.directory.leads_models import Inquiry` next to the existing `ContactReveal` import):

```python
async def test_reveal_records_contact_inquiry_once_per_day(
    api: tuple[httpx.AsyncClient, AsyncSession], reveal_redis: Redis
) -> None:
    """D24.B: a reveal is also a lead — recorded once per user/business/day so
    repeat reveals don't spam the vendor inbox, and NEVER carrying the phone."""
    http, session = api
    owner = uuid.uuid4()
    caller = uuid.uuid4()
    _slug, branch_id = await _seeded_branch(session, owner)
    for _ in range(2):
        ok = await http.post(f"/directory/branches/{branch_id}/reveal", headers=_as(caller))
        assert ok.status_code == 200
    inquiries = (
        await session.scalars(select(Inquiry).where(Inquiry.from_user_id == caller))
    ).all()
    assert len(inquiries) == 1  # deduped
    inquiry = inquiries[0]
    assert inquiry.type == "contact"
    assert inquiry.payload["source"] == "contact_reveal"
    assert inquiry.pincode == "641001"
    # the attribution row records THAT contact happened, never the number
    assert PHONE not in str(inquiry.payload)
    assert WHATSAPP not in str(inquiry.payload)


async def test_second_user_reveal_gets_own_inquiry(
    api: tuple[httpx.AsyncClient, AsyncSession], reveal_redis: Redis
) -> None:
    http, session = api
    owner = uuid.uuid4()
    _slug, branch_id = await _seeded_branch(session, owner)
    for caller in (uuid.uuid4(), uuid.uuid4()):
        ok = await http.post(f"/directory/branches/{branch_id}/reveal", headers=_as(caller))
        assert ok.status_code == 200
    count = len(
        (await session.scalars(select(Inquiry).where(Inquiry.type == "contact"))).all()
    )
    assert count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/Scripts/python.exe -m pytest tests/test_contact_reveal.py -q
```
Expected: both new tests FAIL (`assert len(inquiries) == 1` sees 0); all existing reveal tests pass.

- [ ] **Step 3: Implement the service function**

In `leads_service.py` add to imports: `from datetime import UTC, datetime` and append:

```python
async def record_reveal_inquiry(
    session: AsyncSession, *, user_id: uuid.UUID, business_id: uuid.UUID, pincode: str
) -> Inquiry | None:
    """Attribution lead for a contact reveal (D24.B): the reveal IS a contact
    intent, so it lands in the vendor inbox / response stats like any lead.
    Deduped per (user, business, UTC day) so repeat reveals don't spam the
    inbox. Direct insert, NOT route_inquiry(): the business is already known
    and its branch pincode may legitimately sit outside its coverage list.
    The payload must never carry the revealed number (DPDP)."""
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    existing = await session.scalar(
        select(Inquiry.id).where(
            Inquiry.from_user_id == user_id,
            Inquiry.business_id == business_id,
            Inquiry.type == "contact",
            Inquiry.payload["source"].astext == "contact_reveal",
            Inquiry.created_at >= midnight,
        )
    )
    if existing is not None:
        return None
    inquiry = Inquiry(
        type="contact",
        from_user_id=user_id,
        business_id=business_id,
        payload={
            "message": "Contact number revealed via profile page.",
            "source": "contact_reveal",
        },
        pincode=pincode,
    )
    session.add(inquiry)
    await session.flush()
    return inquiry
```

- [ ] **Step 4: Wire into the reveal handler**

In `router.py`: add `from modules.directory import leads_service` to the imports, then in `reveal_branch_contact` replace the block from `session.add(ContactReveal(...))` through `await session.commit()` with:

```python
    session.add(ContactReveal(user_id=user_id, business_id=branch.business_id, branch_id=branch.id))
    inquiry = await leads_service.record_reveal_inquiry(
        session, user_id=user_id, business_id=branch.business_id, pincode=branch.pincode
    )
    event_payload: dict[str, object] | None = None
    if inquiry is not None and business.owner_user_id is not None:
        # capture BEFORE commit — ORM attributes expire at commit
        event_payload = {
            "user_id": str(business.owner_user_id),
            "inquiry_id": str(inquiry.id),
            "business_id": str(business.id),
            "vars": {"business_name": business.name, "inquiry_type": "contact"},
        }
    await session.commit()
    if event_payload is not None:
        await _publish_best_effort("lead.created", event_payload)
```

(The `logger.info("contact.revealed", ...)` line and the `ContactRevealOut` return stay exactly where they were, after the commit. `_publish_best_effort` already exists in router.py.)

- [ ] **Step 5: Run tests to verify they pass**

```
.venv/Scripts/python.exe -m pytest tests/test_contact_reveal.py tests/test_leads_router.py tests/test_leads_routing.py -q
```
Expected: ALL PASS — including `test_reveal_log_line_has_no_phone` (the no-plaintext-phone gate, non-negotiable 1) and the cap/fail-closed tests.

- [ ] **Step 6: Format and commit**

```
.venv/Scripts/python.exe -m ruff format modules/directory/leads_service.py modules/directory/router.py tests/test_contact_reveal.py
git add -A
git commit -m "feat(d24): reveal records deduped contact-lead for vendor attribution"
```

---

### Task 5: web-milk BFF proxies for directory + reviews

**Files:**
- Create: `apps/web-milk/app/api/directory/[...path]/route.ts`
- Create: `apps/web-milk/app/api/reviews/[[...path]]/route.ts`

**Interfaces:**
- Consumes: `apps/web-milk/lib/auth.ts` (exists — same `auth.getAccessToken()` contract as web-agri).
- Produces: same-origin `/api/directory/*` and `/api/reviews[/*]` used by Task 7's client components.

- [ ] **Step 1: Copy the proxies from web-agri**

Copy `apps/web-agri/app/api/directory/[...path]/route.ts` → `apps/web-milk/app/api/directory/[...path]/route.ts` VERBATIM (it imports `@/lib/auth`, which resolves to web-milk's own lib in the new app; keep the raw-bytes forwarding and path-traversal guard exactly as-is).

Copy `apps/web-agri/app/api/reviews/[[...path]]/route.ts` → `apps/web-milk/app/api/reviews/[[...path]]/route.ts` VERBATIM (optional catch-all is load-bearing: `POST /api/reviews` has zero path segments).

- [ ] **Step 2: Typecheck**

```
pnpm --filter @agri/web-milk typecheck
```
Expected: exit 0.

- [ ] **Step 3: Commit**

```
git add apps/web-milk/app/api
git commit -m "feat(d24): web-milk BFF proxies for directory reveal + reviews"
```

---

### Task 6: Vendor profile page (server-rendered core + JSON-LD)

**Files:**
- Create: `apps/web-milk/lib/business.ts`
- Create: `apps/web-milk/app/directory/businesses/[slug]/page.tsx`
- Create: `apps/web-milk/app/directory/businesses/[slug]/reviews-section.tsx`

**Interfaces:**
- Consumes: `GET /directory/businesses/{slug}` (with Task 3's `coverage_pincodes`), `GET /catalog/businesses/{slug}/products`, `GET /reviews` + `GET /reviews/summary` (public reads, direct to backend).
- Produces: ISR page at `/directory/businesses/[slug]` — the canonical URL D23 JSON-LD already emits. `lib/business.ts` exports `fetchBusiness`, `fetchProducts`, `fetchReviews`, and types `BusinessDetail`, `PublicBranch`, `CatalogProduct`, `RatingSummary`, `ReviewItem` (Task 7 components consume `RatingSummary`/`ReviewItem`).

- [ ] **Step 1: Write `apps/web-milk/lib/business.ts`**

```ts
const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export type LocalizedText = Record<string, string>;

export interface PublicBranch {
  id: string;
  business_id: string;
  address: string;
  state: string;
  district: string;
  pincode: string;
  lat: number | null;
  lng: number | null;
  hours: Record<string, unknown>;
}

export interface BusinessDetail {
  business: {
    id: string;
    name: string;
    slug: string;
    type: string;
    status: string;
    verification_status: string;
    subscription_tier: string;
    claimable: boolean;
    primary_pincode: string;
    description: LocalizedText | null;
  };
  branches: PublicBranch[];
  categories: { id: string; slug: string; name: LocalizedText }[];
  coverage_pincodes: string[];
}

export interface CatalogProduct {
  id: string;
  name: string;
  slug: string;
  specs: Record<string, unknown>;
  price_display: string | null;
  images: string[];
}

export type RatingSummary = { rating_avg: string | null; rating_count: number };
export type ReviewItem = {
  id: string;
  rating: number;
  body: LocalizedText | null;
  created_at: string;
};

/** Server-side public read, direct to backend (mirrors web-agri's business
 * page): 404 -> null (notFound), other non-ok -> throw (real error). */
export async function fetchBusiness(slug: string): Promise<BusinessDetail | null> {
  const res = await fetch(`${API}/directory/businesses/${encodeURIComponent(slug)}`, {
    next: { revalidate: 300 },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`directory fetch failed: ${res.status}`);
  return (await res.json()) as BusinessDetail;
}

/** Tolerant: a missing/failed catalog read degrades to an empty product list
 * rather than failing the whole profile render. */
export async function fetchProducts(slug: string): Promise<CatalogProduct[]> {
  try {
    const res = await fetch(
      `${API}/catalog/businesses/${encodeURIComponent(slug)}/products?limit=50`,
      { next: { revalidate: 300 } },
    );
    if (!res.ok) return [];
    return ((await res.json()) as { items: CatalogProduct[] }).items;
  } catch {
    return [];
  }
}

/** Public review reads — NOT via /api/reviews (that proxy is auth-required
 * by design and would 401 guests). Tolerant of non-ok responses. */
export async function fetchReviews(
  businessId: string,
): Promise<{ summary: RatingSummary; items: ReviewItem[] }> {
  const qs = `target_type=business&target_id=${businessId}`;
  const [summaryRes, listRes] = await Promise.all([
    fetch(`${API}/reviews/summary?${qs}`, { next: { revalidate: 300 } }),
    fetch(`${API}/reviews?${qs}&limit=10`, { next: { revalidate: 300 } }),
  ]);
  const summary: RatingSummary = summaryRes.ok
    ? ((await summaryRes.json()) as RatingSummary)
    : { rating_avg: null, rating_count: 0 };
  const items: ReviewItem[] = listRes.ok
    ? ((await listRes.json()) as { items: ReviewItem[] }).items
    : [];
  return { summary, items };
}
```

- [ ] **Step 2: Copy `reviews-section.tsx`**

Copy `apps/web-agri/app/directory/businesses/[slug]/reviews-section.tsx` → `apps/web-milk/app/directory/businesses/[slug]/reviews-section.tsx`, with ONE change: delete its local `RatingSummary`/`ReviewItem`/`LocalizedText` type declarations and import them instead:

```ts
import type { RatingSummary, ReviewItem } from "@/lib/business";
```
(Keep the re-export line `export type { RatingSummary, ReviewItem };` OUT — pages import types from `@/lib/business` directly.)

- [ ] **Step 3: Write `page.tsx`**

`apps/web-milk/app/directory/businesses/[slug]/page.tsx`:

```tsx
import { Badge, Card, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import {
  fetchBusiness,
  fetchProducts,
  fetchReviews,
  type BusinessDetail,
  type CatalogProduct,
  type PublicBranch,
  type RatingSummary,
} from "@/lib/business";

import { ReviewsSection } from "./reviews-section";

const SITE = "https://milk.in";

export const revalidate = 300;

function canonicalFor(slug: string): string {
  return canonicalUrl(SITE, `/directory/businesses/${slug}`);
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const detail = await fetchBusiness(slug);
  if (!detail) {
    return { title: "Vendor not found", robots: { index: false, follow: true } };
  }
  const { business } = detail;
  const description =
    business.description?.en ??
    `Milk from ${business.name} — prices, coverage and contact on Milk.in.`;
  return buildMetadata({
    title: `${business.name} | Milk.in`,
    description,
    canonical: canonicalFor(business.slug),
    siteName: "Milk.in",
  });
}

/**
 * Hand-built LocalBusiness JSON-LD (same precedent as web-agri's business
 * page: the shared builder requires `address`, only known when a branch
 * exists). `<` escaped so content can never close the script tag.
 * NON-NEGOTIABLE 2: must parse as valid LocalBusiness.
 */
function businessJsonLd(
  detail: BusinessDetail,
  canonical: string,
  summary: RatingSummary,
): string {
  const { business, branches } = detail;
  const firstBranch = branches[0];
  const data = {
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    name: business.name,
    url: canonical,
    ...(business.description?.en ? { description: business.description.en } : {}),
    ...(firstBranch
      ? {
          address: {
            "@type": "PostalAddress",
            streetAddress: firstBranch.address,
            addressLocality: firstBranch.district,
            addressRegion: firstBranch.state,
            postalCode: firstBranch.pincode,
            addressCountry: "IN",
          },
        }
      : {}),
    ...(firstBranch?.lat != null && firstBranch?.lng != null
      ? {
          geo: {
            "@type": "GeoCoordinates",
            latitude: firstBranch.lat,
            longitude: firstBranch.lng,
          },
        }
      : {}),
    ...(summary.rating_count > 0
      ? {
          aggregateRating: {
            "@type": "AggregateRating",
            ratingValue: summary.rating_avg,
            ratingCount: summary.rating_count,
          },
        }
      : {}),
  };
  return JSON.stringify(data).replaceAll("<", "\\u003c");
}

function specText(specs: Record<string, unknown>, key: string): string | null {
  const value = specs[key];
  return typeof value === "string" && value ? value : null;
}

function ProductCardLite({ product }: { product: CatalogProduct }) {
  const meta = [specText(product.specs, "milk_type"), specText(product.specs, "pack_size")]
    .filter(Boolean)
    .join(" · ");
  return (
    <Card className="space-y-1 p-3">
      <h3 className="text-[14.5px] font-extrabold leading-[1.3] text-ink">{product.name}</h3>
      {meta ? <p className="text-[12.5px] text-sub">{meta}</p> : null}
      {product.price_display ? (
        <p className="text-[15px] font-extrabold text-ink">{product.price_display}</p>
      ) : null}
    </Card>
  );
}

/** Delivery windows render from Branch.hours (free-shape JSONB) — structured
 * delivery-window schema is deferred (design decision 3). */
function BranchHours({ branch }: { branch: PublicBranch }) {
  const entries = Object.entries(branch.hours);
  if (entries.length === 0) return null;
  return (
    <p className="text-[12.5px] text-sub">
      {entries.map(([label, value]) => `${label}: ${String(value)}`).join(" · ")}
    </p>
  );
}

const MAX_PINCODES_SHOWN = 12;

export default async function VendorProfilePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const detail = await fetchBusiness(slug);
  if (!detail) notFound();
  const { business, branches, coverage_pincodes } = detail;
  const canonical = canonicalFor(business.slug);
  const [products, { summary, items: reviews }] = await Promise.all([
    fetchProducts(business.slug),
    fetchReviews(business.id),
  ]);
  const shownPincodes = coverage_pincodes.slice(0, MAX_PINCODES_SHOWN);
  const morePincodes = coverage_pincodes.length - shownPincodes.length;

  return (
    <main>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: businessJsonLd(detail, canonical, summary) }}
      />
      <Wrap className="max-w-[720px] py-6">
        <header className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-display text-[26px] font-extrabold text-ink">{business.name}</h1>
            {business.verification_status === "verified" ? (
              <Badge variant="verified">✔ Verified</Badge>
            ) : null}
          </div>
          <p className="text-[13px] font-semibold text-sub">
            {business.type} · {business.primary_pincode}
          </p>
          {business.description?.en ? (
            <p className="text-[15px] text-ink">{business.description.en}</p>
          ) : null}
        </header>

        {products.length > 0 ? (
          <section className="mt-6 space-y-2.5" aria-labelledby="products-h">
            <h2 id="products-h" className="font-display text-[16px] font-extrabold text-ink">
              Milk products
            </h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {products.map((product) => (
                <ProductCardLite key={product.id} product={product} />
              ))}
            </div>
          </section>
        ) : null}

        {coverage_pincodes.length > 0 ? (
          <section className="mt-6 space-y-1.5" aria-labelledby="coverage-h">
            <h2 id="coverage-h" className="font-display text-[16px] font-extrabold text-ink">
              Delivery area
            </h2>
            <p className="text-[12.5px] text-sub" data-testid="coverage-pincodes">
              {shownPincodes.join(", ")}
              {morePincodes > 0 ? ` + ${morePincodes} more` : ""}
            </p>
          </section>
        ) : null}

        {branches.length > 0 ? (
          <section className="mt-6 space-y-2.5" aria-labelledby="branches-h">
            <h2 id="branches-h" className="font-display text-[16px] font-extrabold text-ink">
              Branches &amp; delivery hours
            </h2>
            <ul className="space-y-2">
              {branches.map((branch) => (
                <li key={branch.id}>
                  <Card className="space-y-2 p-3">
                    <p className="text-[13.5px] font-semibold text-ink">{branch.address}</p>
                    <p className="text-[12.5px] text-sub">
                      {branch.district}, {branch.state} {branch.pincode}
                    </p>
                    <BranchHours branch={branch} />
                  </Card>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <ReviewsSection summary={summary} items={reviews} />
      </Wrap>
    </main>
  );
}
```

- [ ] **Step 4: Typecheck + lint**

```
pnpm --filter @agri/web-milk typecheck
pnpm --filter @agri/web-milk lint
```
Expected: exit 0 for both.

- [ ] **Step 5: Commit**

```
git add apps/web-milk/lib/business.ts "apps/web-milk/app/directory"
git commit -m "feat(d24): milk vendor profile page (SSR + LocalBusiness JSON-LD)"
```

---

### Task 7: Tracked contact + review-write client islands

**Files:**
- Create: `apps/web-milk/app/directory/businesses/[slug]/reveal-contact.tsx`
- Create: `apps/web-milk/app/directory/businesses/[slug]/lead-form.tsx`
- Create: `apps/web-milk/app/directory/businesses/[slug]/review-form.tsx`
- Modify: `apps/web-milk/app/directory/businesses/[slug]/page.tsx`
- Modify: `apps/web-milk/package.json` (add `"@agri/auth-client": "workspace:*"` if missing — check first; the D23 header already uses it, so it should exist)

**Interfaces:**
- Consumes: Task 5 proxies (`POST /api/directory/branches/{id}/reveal`, `POST /api/reviews`), existing `/api/leads/inquiries` proxy, `useAgriUser` from `@agri/auth-client/react`.
- Produces: `RevealContact({ branchId, slug })`, `LeadForm({ businessId, defaultPincode, milkVertical })`, `ReviewForm({ businessId, slug })` — page-local components.

- [ ] **Step 1: Port the three components from web-agri**

Copy VERBATIM from `apps/web-agri/app/directory/businesses/[slug]/`:
- `reveal-contact.tsx` (login gate → capped reveal → CallButton/WhatsAppButton; 429 → "Daily reveal limit reached — try tomorrow."). No changes needed — the `next=` login redirect path `/directory/businesses/${slug}` is the same in web-milk.
- `lead-form.tsx` (guest-capable `POST /api/leads/inquiries`; the web-milk `/api/leads` proxy already exists from D23).
- `review-form.tsx` (login gate → `POST /api/reviews`; 201 → "visible after moderation", 409 → "already reviewed").

- [ ] **Step 2: Wire into `page.tsx`**

Add imports:

```tsx
import { LeadForm } from "./lead-form";
import { RevealContact } from "./reveal-contact";
import { ReviewForm } from "./review-form";
```

Inside the branches `<Card>` (after the `<BranchHours branch={branch} />` line) add:

```tsx
                    <RevealContact branchId={branch.id} slug={business.slug} />
```

After the branches section (before `<ReviewsSection ...>`) add:

```tsx
        <div className="mt-6">
          <LeadForm
            businessId={business.id}
            defaultPincode={business.primary_pincode}
            milkVertical={business.type === "vendor"}
          />
        </div>
```

After `<ReviewsSection summary={summary} items={reviews} />` add:

```tsx
        <div className="mt-6">
          <ReviewForm businessId={business.id} slug={business.slug} />
        </div>
```

- [ ] **Step 3: Typecheck + lint + build**

```
pnpm --filter @agri/web-milk typecheck
pnpm --filter @agri/web-milk lint
pnpm --filter @agri/web-milk build
```
Expected: all exit 0. The build output should list `/directory/businesses/[slug]` as ISR (`revalidate: 300`).

- [ ] **Step 4: Commit**

```
git add apps/web-milk
git commit -m "feat(d24): tracked contact reveal + lead fallback + review write on profile"
```

---

### Task 8: Vendor cards link to profiles and become selectable

**Files:**
- Modify: `apps/web-milk/app/[pincode]/vendor-card.tsx`
- Modify: `apps/web-milk/lib/milk.ts` (MilkCard type gains `lat`/`lng`)

**Interfaces:**
- Consumes: `MilkCardOut.lat/lng` from Task 2 (wire), profile route from Task 6.
- Produces: `VendorCard({ card, selected?, onSelect? })` — client component; container carries `data-testid="vendor-card-{slug}"`, `data-card-id={id}`, `data-selected`. `MilkCard` TS type gains `lat: number | null; lng: number | null` (consumed by Task 9).

- [ ] **Step 1: Extend `lib/milk.ts`**

In the `MilkCard` interface, after `distance_m: number;` add:

```ts
  lat: number | null;
  lng: number | null;
```

- [ ] **Step 2: Rewrite `vendor-card.tsx`**

```tsx
"use client";

import { Badge, buttonVariants, Card, cn } from "@agri/ui";
import Link from "next/link";

import { milkTypeMeta, type MilkCard } from "@/lib/milk";

/**
 * ListingCard anatomy (design-system.md §2, `.card.lc`): badge row → title +
 * meta → optional price-tag → Call/WA action row. D24 wires the D23
 * placeholder actions: Call/WhatsApp now link to the vendor profile, where
 * the D18 capped reveal flow lives (numbers are NEVER in list payloads).
 *
 * Selection (map↔list sync, D24.D): `selected`/`onSelect` come from the
 * VendorResults island. Container click selects; profile navigation happens
 * only via the explicit action links so a selection tap never navigates.
 */
export function VendorCard({
  card,
  selected = false,
  onSelect,
}: {
  card: MilkCard;
  selected?: boolean;
  onSelect?: (id: string) => void;
}) {
  const km = (card.distance_m / 1000).toFixed(1);
  const priceLine = card.products
    .filter((p) => p.price_display)
    .map((p) => `${p.price_display} ${milkTypeMeta(p.milk_type ?? "").en}`.trim())
    .join(" · ");
  const profileHref = `/directory/businesses/${card.slug}`;

  return (
    <Card
      data-testid={`vendor-card-${card.slug}`}
      data-card-id={card.id}
      data-selected={selected}
      onClick={onSelect ? () => onSelect(card.id) : undefined}
      className={cn(
        "flex flex-col gap-1.5 p-4",
        selected && "outline outline-[3px] outline-accent outline-offset-2",
      )}
    >
      {card.verification_status === "verified" ? (
        <Badge variant="verified">✔ Verified</Badge>
      ) : null}
      <h3 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">{card.name}</h3>
      <p className="text-[12.5px] text-sub">{km} km away</p>
      {priceLine ? <p className="text-[15px] font-extrabold text-ink">{priceLine}</p> : null}
      <div className="mt-1 flex gap-2">
        <Link
          href={profileHref}
          className={cn(buttonVariants({ variant: "call" }), "no-underline")}
          onClick={(event) => event.stopPropagation()}
        >
          📞 Call
        </Link>
        <Link
          href={profileHref}
          className={cn(buttonVariants({ variant: "wa" }), "no-underline")}
          onClick={(event) => event.stopPropagation()}
        >
          WhatsApp
        </Link>
      </div>
    </Card>
  );
}
```

(Call/WhatsApp both land on the profile because the actual numbers only exist behind the login-gated, capped reveal there — an un-gated `tel:` link from the list is exactly what the DO-NOT forbids.)

- [ ] **Step 3: Typecheck + lint**

```
pnpm --filter @agri/web-milk typecheck && pnpm --filter @agri/web-milk lint
```
Expected: exit 0. (`page.tsx` still renders `VendorCard` without the new optional props — fine.)

- [ ] **Step 4: Commit**

```
git add apps/web-milk
git commit -m "feat(d24): vendor cards link to profile, gain selection affordance"
```

---

### Task 9: Map + list sync on the pincode page

**Files:**
- Modify: `apps/web-milk/package.json` (add `maplibre-gl`)
- Modify: `backend/core/scripts/seed_e2e_milk.py` (branch coords + backfill)
- Create: `apps/web-milk/app/[pincode]/vendor-results.tsx`
- Create: `apps/web-milk/app/[pincode]/vendor-map.tsx`
- Modify: `apps/web-milk/app/[pincode]/page.tsx`

**Interfaces:**
- Consumes: `MilkCard.lat/lng` (Tasks 2 + 8), `VendorCard` selection props (Task 8).
- Produces: `VendorResults({ vendors, brands })` client island (owns selection state + map toggle); `VendorMap` (default export) with props `{ cards: MapPin[], selectedId: string | null, onSelect: (id: string) => void }` where `MapPin = { id: string; slug: string; name: string; lat: number; lng: number }`. Pins carry `data-testid="map-pin-{slug}"` + `data-selected`; toggle carries `data-testid="map-toggle"`.

- [ ] **Step 1: Add the dependency**

```
pnpm --filter @agri/web-milk add maplibre-gl
```
Then open `apps/web-milk/package.json` and pin the exact version (strip any `^` — this repo pins exact versions). Expected: `maplibre-gl` appears in dependencies; `pnpm-lock.yaml` updated. (maplibre-gl has no postinstall build script, so the pnpm `allowBuilds` trap does not apply.)

- [ ] **Step 2: Seed coords (E2E map pins need them)**

In `backend/core/scripts/seed_e2e_milk.py`:

(a) Add imports: `from decimal import Decimal` and extend the models import to `from modules.directory.models import Branch, Business`.

(b) Add module constants after `_PINCODE`:

```python
_BRANCH_LAT = Decimal("10.923220")  # 641001 centroid — deterministic map pin
_BRANCH_LNG = Decimal("76.968600")
```

(c) Replace the early-return block so an existing seed gets coords backfilled (idempotent both ways):

```python
        existing = await session.scalar(select(Business).where(Business.name == _BUSINESS_NAME))
        if existing is not None:
            branch = await session.scalar(
                select(Branch).where(Branch.business_id == existing.id)
            )
            if branch is not None and branch.lat is None:
                branch.lat = _BRANCH_LAT
                branch.lng = _BRANCH_LNG
                await session.commit()
                print("seed_e2e_milk: backfilled branch coords")  # noqa: T201
            else:
                print("seed_e2e_milk: already present, nothing to do")  # noqa: T201
            return
```

(d) Add `lat=_BRANCH_LAT, lng=_BRANCH_LNG,` to the `service.add_branch(...)` call (after `pincode=_PINCODE,`).

Run `.venv/Scripts/python.exe -m ruff format scripts/seed_e2e_milk.py` from `backend/core`.

- [ ] **Step 3: Write `vendor-map.tsx`**

```tsx
"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";

export interface MapPin {
  id: string;
  slug: string;
  name: string;
  lat: number;
  lng: number;
}

/**
 * MapLibre only (D24 DO-NOT: no Google Maps JS). Raster OSM tiles keep the
 * style self-contained — swap the tile URL for a paid provider before real
 * traffic (OSM tile policy). Pins are DOM Markers, not GL symbol layers:
 * covers() pages cap the list at 20 cards, so pin count never reaches
 * clustering territory, and DOM pins are click-syncable + testable
 * (NON-NEGOTIABLE 3). Same-coordinate pins get a tiny deterministic spread
 * so none are unreachable.
 */
const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

const PIN_CLASS =
  "block h-7 w-7 cursor-pointer rounded-full border-2 border-card bg-brand-deep shadow-md";
const PIN_SELECTED_CLASS =
  "block h-7 w-7 cursor-pointer rounded-full border-2 border-card bg-accent shadow-md";

function spread(pins: MapPin[]): MapPin[] {
  const seen = new Map<string, number>();
  return pins.map((pin) => {
    const key = `${pin.lat.toFixed(4)}:${pin.lng.toFixed(4)}`;
    const n = seen.get(key) ?? 0;
    seen.set(key, n + 1);
    return n === 0 ? pin : { ...pin, lat: pin.lat + n * 0.0004, lng: pin.lng + n * 0.0004 };
  });
}

export default function VendorMap({
  cards,
  selectedId,
  onSelect,
}: {
  cards: MapPin[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<Map<string, maplibregl.Marker>>(new Map());
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: OSM_STYLE,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }));
    const pins = spread(cards);
    const bounds = new maplibregl.LngLatBounds();
    for (const pin of pins) {
      const el = document.createElement("button");
      el.type = "button";
      el.setAttribute("data-testid", `map-pin-${pin.slug}`);
      el.setAttribute("data-pin-id", pin.id);
      el.setAttribute("aria-label", pin.name);
      el.className = PIN_CLASS;
      el.addEventListener("click", (event) => {
        event.stopPropagation();
        onSelectRef.current(pin.id);
      });
      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([pin.lng, pin.lat])
        .addTo(map);
      markersRef.current.set(pin.id, marker);
      bounds.extend([pin.lng, pin.lat]);
    }
    if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 48, maxZoom: 14 });
    mapRef.current = map;
    return () => {
      markersRef.current.clear();
      map.remove();
      mapRef.current = null;
    };
    // cards are stable for a given SSR page load — init once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    for (const [id, marker] of markersRef.current) {
      const el = marker.getElement();
      const selected = id === selectedId;
      el.className = selected ? PIN_SELECTED_CLASS : PIN_CLASS;
      el.setAttribute("data-selected", String(selected));
    }
    if (selectedId) {
      const marker = markersRef.current.get(selectedId);
      if (marker && mapRef.current) {
        mapRef.current.flyTo({ center: marker.getLngLat(), zoom: 13 });
      }
    }
  }, [selectedId]);

  return (
    <div
      ref={containerRef}
      data-testid="vendor-map"
      className="h-[320px] w-full overflow-hidden rounded-card border border-line"
    />
  );
}
```

- [ ] **Step 4: Write `vendor-results.tsx`**

```tsx
"use client";

import { Button } from "@agri/ui";
import dynamic from "next/dynamic";
import { useRef, useState } from "react";

import type { MilkCard } from "@/lib/milk";

import { VendorCard } from "./vendor-card";
import type { MapPin } from "./vendor-map";

// MapLibre is ~200KB of client JS: dynamic + ssr:false keeps it entirely out
// of the SSR/ISR payload; it only loads when the user opens the map
// (Lighthouse ≥90 on this audited page — NON-NEGOTIABLE 4 guard).
const VendorMap = dynamic(() => import("./vendor-map"), { ssr: false });

export function VendorResults({
  vendors,
  brands,
}: {
  vendors: MilkCard[];
  brands: MilkCard[];
}) {
  const [showMap, setShowMap] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const pins: MapPin[] = [...vendors, ...brands]
    .filter((c) => c.lat !== null && c.lng !== null)
    .map((c) => ({ id: c.id, slug: c.slug, name: c.name, lat: c.lat as number, lng: c.lng as number }));

  const selectFromMap = (id: string) => {
    setSelectedId(id);
    listRef.current
      ?.querySelector(`[data-card-id="${id}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const renderSection = (title: string, cards: MilkCard[]) =>
    cards.length > 0 ? (
      <section className="flex flex-col gap-2.5">
        <h2 className="font-display text-[16px] font-extrabold text-ink">{title}</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {cards.map((c) => (
            <VendorCard key={c.id} card={c} selected={selectedId === c.id} onSelect={setSelectedId} />
          ))}
        </div>
      </section>
    ) : null;

  return (
    <div ref={listRef} className="flex flex-col gap-5">
      {pins.length > 0 ? (
        <div>
          <Button
            variant="ghost"
            data-testid="map-toggle"
            className="max-w-[200px]"
            aria-expanded={showMap}
            onClick={() => setShowMap((v) => !v)}
          >
            {showMap ? "Hide map" : "🗺 Show map"}
          </Button>
          {showMap ? (
            <div className="mt-3">
              <VendorMap cards={pins} selectedId={selectedId} onSelect={selectFromMap} />
            </div>
          ) : null}
        </div>
      ) : null}
      {renderSection("Local vendors", vendors)}
      {renderSection("Brands & shops nearby", brands)}
    </div>
  );
}
```

(If `Button` doesn't forward `data-testid`, wrap the toggle in a plain `<button>` with `buttonVariants({ variant: "ghost" })` classes instead — check `packages/ui/src/components/button.tsx`: it spreads props, so `data-testid` passes through.)

- [ ] **Step 5: Wire into `app/[pincode]/page.tsx`**

Add import: `import { VendorResults } from "./vendor-results";` and remove the now-unused `import { VendorCard } from "./vendor-card";`.

Replace the covered-branch fragment that renders the two sections (the whole `<>...</>` block inside the `filteredEmpty ? ... : (...)` else-arm) with:

```tsx
        <VendorResults vendors={data.vendors} brands={data.brands} />
```

(The `filteredEmpty` message, price banner, filter row, JSON-LD, and headings above stay server-rendered exactly as they are.)

- [ ] **Step 6: Typecheck + lint + build**

```
pnpm --filter @agri/web-milk typecheck
pnpm --filter @agri/web-milk lint
pnpm --filter @agri/web-milk build
```
Expected: exit 0; the `/[pincode]` first-load JS should NOT include maplibre (dynamic chunk).

- [ ] **Step 7: Commit**

```
git add apps/web-milk backend/core/scripts/seed_e2e_milk.py pnpm-lock.yaml
git commit -m "feat(d24): lazy MapLibre map with list-synced vendor pins"
```

---

### Task 10: E2E — vendor profile (JSON-LD, gated reveal, lead form)

**Files:**
- Create: `e2e/vendor-profile.spec.ts`

**Interfaces:**
- Consumes: seeded vendor (`E2E Milk Vendor`, slug `e2e-milk-vendor`, covers 641001) from `seed_e2e_milk.py`; backend at `http://localhost:8000`; web-milk at `http://localhost:3000`.

- [ ] **Step 1: Write the spec**

```ts
import { expect, type Page, test } from "@playwright/test";

const MILK = "http://localhost:3000";
const API = "http://localhost:8000";

/** Same convention as e2e/milk-home.spec.ts: wait out the silent-SSO bounce
 * before interacting. */
async function waitForHeaderSettled(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: /^login$/i })).toBeVisible({ timeout: 20_000 });
}

/** Resolve the seeded vendor's slug from the live API instead of hardcoding
 * it — survives seed renames. */
async function seededSlug(request: import("@playwright/test").APIRequestContext): Promise<string> {
  const res = await request.get(`${API}/catalog/milk/home/641001`);
  expect(res.ok()).toBeTruthy();
  const data = (await res.json()) as { vendors: { slug: string }[] };
  expect(data.vendors.length).toBeGreaterThan(0);
  return data.vendors[0].slug;
}

test.describe("D24 vendor profile", () => {
  test("renders with valid LocalBusiness JSON-LD (non-negotiable 2)", async ({
    page,
    request,
  }) => {
    const slug = await seededSlug(request);
    await page.goto(`${MILK}/directory/businesses/${slug}`);
    await waitForHeaderSettled(page);
    const raw = await page.locator('script[type="application/ld+json"]').first().textContent();
    expect(raw).toBeTruthy();
    const data = JSON.parse(raw as string) as Record<string, unknown>;
    expect(data["@context"]).toBe("https://schema.org");
    expect(data["@type"]).toBe("LocalBusiness");
    expect(data["name"]).toBeTruthy();
    expect(String(data["url"])).toContain(`/directory/businesses/${slug}`);
    const address = data["address"] as Record<string, unknown>;
    expect(address["@type"]).toBe("PostalAddress");
    expect(address["postalCode"]).toBe("641001");
  });

  test("guest sees login-gated contact, never a phone number", async ({ page, request }) => {
    const slug = await seededSlug(request);
    await page.goto(`${MILK}/directory/businesses/${slug}`);
    await waitForHeaderSettled(page);
    await expect(page.getByText(/login to view contact/i)).toBeVisible();
    // the seeded number must not be anywhere in the SSR payload
    const html = await page.content();
    expect(html).not.toContain("9876500023");
  });

  test("guest can send a contact lead via the form fallback", async ({ page, request }) => {
    const slug = await seededSlug(request);
    await page.goto(`${MILK}/directory/businesses/${slug}`);
    await waitForHeaderSettled(page);
    await page.getByLabel(/message/i).fill("Do you deliver on Sundays?");
    await page.getByRole("button", { name: /send enquiry/i }).click();
    await expect(page.getByText(/enquiry sent/i)).toBeVisible();
  });
});
```

- [ ] **Step 2: Run the spec**

```
cd d:\agri-ecosystem
pnpm e2e -- vendor-profile.spec.ts
```
Expected: 3 passed. (First run boots migrations + geo load + seed; give it time. If the seed pre-existed without coords, the Step-2-Task-9 backfill runs automatically via e2e-api.mjs.)

- [ ] **Step 3: Commit**

```
git add e2e/vendor-profile.spec.ts
git commit -m "test(d24): vendor profile e2e — JSON-LD, gated reveal, lead fallback"
```

---

### Task 11: E2E — map↔list selection sync

**Files:**
- Create: `e2e/map-sync.spec.ts`

- [ ] **Step 1: Write the spec**

```ts
import { expect, type Page, test } from "@playwright/test";

const MILK = "http://localhost:3000";

async function waitForHeaderSettled(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: /^login$/i })).toBeVisible({ timeout: 20_000 });
}

test.describe("D24 map ↔ list sync (non-negotiable 3)", () => {
  test("pin click highlights the card; card click highlights the pin", async ({ page }) => {
    await page.goto(`${MILK}/641001`);
    await waitForHeaderSettled(page);

    await page.getByTestId("map-toggle").click();
    await expect(page.getByTestId("vendor-map")).toBeVisible();

    // --- pin → card ---
    const pin = page.locator('[data-testid^="map-pin-"]').first();
    await expect(pin).toBeVisible({ timeout: 15_000 }); // marker mounts with the lazy chunk
    await pin.click();
    const selectedCard = page.locator('[data-testid^="vendor-card-"][data-selected="true"]');
    await expect(selectedCard).toBeVisible();

    // --- card → pin --- (click top-left corner: selection zone, no links there)
    const otherCard = page.locator('[data-testid^="vendor-card-"]').last();
    await otherCard.click({ position: { x: 8, y: 8 } });
    const otherId = await otherCard.getAttribute("data-card-id");
    const selectedPin = page.locator('[data-testid^="map-pin-"][data-selected="true"]');
    await expect(selectedPin).toBeVisible();
    await expect(selectedPin).toHaveAttribute("data-pin-id", otherId as string);
  });
});
```

(With a single seeded vendor, `.first()` and `.last()` are the same card — the assertions still verify both sync directions. If a second seeded vendor exists by then, the test gets stronger for free.)

- [ ] **Step 2: Run the spec**

```
pnpm e2e -- map-sync.spec.ts
```
Expected: 1 passed. Tiles may 404 offline — the test only depends on markers, which render regardless.

- [ ] **Step 3: Commit**

```
git add e2e/map-sync.spec.ts
git commit -m "test(d24): map-list selection sync e2e"
```

---

### Task 12: Full gates, local Lighthouse, PR

**Files:**
- No new files (PR + verification only). Optionally Modify: `.claude/…` nothing — leave the pre-existing `.claude/settings.json` local modification OUT of the PR (do not `git add` it).

- [ ] **Step 1: Backend gates**

```
cd d:\agri-ecosystem\backend\core
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe -m mypy .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/lint-imports.exe
python scripts/dump_public_routes.py --check
```
Expected: all pass; public routes unchanged. (If `lint-imports.exe` isn't at that path, run `.venv/Scripts/python.exe -m importlinter.cli` — whichever the repo's CI job uses.)

- [ ] **Step 2: Frontend gates**

```
cd d:\agri-ecosystem
pnpm check:hex
pnpm --filter @agri/web-milk typecheck
pnpm --filter @agri/web-milk lint
pnpm turbo run build --filter=@agri/web-milk
```
Expected: all pass.

- [ ] **Step 3: Full E2E**

```
pnpm e2e
```
Expected: all specs pass (auth, sso, bff-path-traversal, milk-home, vendor-profile, map-sync).

- [ ] **Step 4: Local Lighthouse on the profile page (non-negotiable 4)**

With the backend running (`.venv/Scripts/python.exe -m uvicorn main:app --port 8000` from backend/core, docker services up) and web-milk built + started (`pnpm --filter @agri/web-milk build && pnpm --filter @agri/web-milk start`):

```
pnpm dlx lighthouse http://localhost:3000/directory/businesses/e2e-milk-vendor --only-categories=performance,accessibility,seo --form-factor=mobile --screenEmulation.mobile --output=json --output-path=./lh-d24-profile.json --chrome-flags="--headless=new"
```

Read the three category scores from `lh-d24-profile.json`. Expected: performance ≥ 0.90, accessibility ≥ 0.95, seo ≥ 0.90 (D23 lesson: local scores are the floor CI can't measure — record the numbers). Also run it against `http://localhost:3000/641001` to confirm the map island didn't regress the pincode page. Delete `lh-d24-profile.json` afterwards (don't commit it).

If performance < 0.90: check that maplibre is NOT in the first-load chunks (`pnpm --filter @agri/web-milk build` output) and that profile-page images aren't unoptimized — fix before opening the PR.

- [ ] **Step 5: Push and open the PR**

```
git push -u origin feat/d24-vendor-profiles
```

Open a PR to **dev** (never main) titled `feat(d24): vendor profiles` using the same GitHub-API/credential-fill flow as D18/D12 (no `gh` CLI on this box). PR body: summary of the 4 design decisions, the non-negotiables each with its test evidence (reveal-cap+no-phone → `test_contact_reveal.py`, JSON-LD → `vendor-profile.spec.ts`, map-sync → `map-sync.spec.ts`, Lighthouse → local scores from Step 4), and end with:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

---

## Self-review notes (already applied)

- Spec coverage: A → Task 6/7 (profile, products, coverage, hours, badge, JSON-LD); B → Tasks 4+7 (reveal via D18 caps + attribution inquiry, no phone in logs test kept green); C → Task 7 lead-form (guest-capable proxy exists); D → Tasks 1/2/8/9/11 (coords, island, sync, distance order preserved); E → Tasks 6/7 (reviews read + gated write, pending default untouched). DO-NOTs: no uncapped reveal (list links go to the gated profile), no auto-publish, no phone in URLs/logs, MapLibre only.
- Clustering: covers() pages cap cards at 20 (`DEFAULT_PAGE_SIZE`), so "cluster if many" is unreachable at current page size; same-coordinate pins get a deterministic spread instead. Documented in `vendor-map.tsx` and to be noted in the PR body.
- Types consistent across tasks: `CoversItem.lat/lng: Decimal|None` → `MilkCardOut.lat/lng: float|None` → `MilkCard.lat/lng: number|null` → `MapPin.lat/lng: number`.
