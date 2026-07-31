# M2 Ad Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mount the live-but-unmounted D21 ads engine on every Milk page: one `AdSlot` primitive, a global sliding `AdCarousel` head banner, four page-level slots, house-ad fill, and category-targetable inventory.

**Architecture:** The D21 serving surface (`GET /ads/serve`, `POST /ads/impressions|clicks`, flag-gated by `ads_enabled`) already exists. We extend it minimally (5 milk slot keys, optional `category` + `count` + optional `pincode` on serve, `categories` in placement targeting), seed house ads server-side, and build the vertical-agnostic frontend primitives in `packages/ui` (AdImage/SponsoredBadge atoms, AdSlot molecule with IntersectionObserver-gated impressions, AdCarousel organism). web-milk gets a `/api/ads` BFF proxy (copied from web-agri) and five mounts. Every slot reserves fixed height while loading and renders a local house fallback when the engine returns nothing — surfaces never empty, CLS stays 0 even with the flag off or an ad-blocker active.

**Tech Stack:** FastAPI + SQLAlchemy async (backend/core), Next.js 15 App Router + Tailwind tokens (apps/web-milk, packages/ui), vitest (node env, lib-only), Playwright (e2e/), pytest.

## Global Constraints

- NEVER commit to `dev` or `main`. Work on `feat/m2-ad-surfaces`, PR targets `dev`. Commit title convention: `feat(m2): ...` (PR title CI check).
- Tokens only — no raw hex/rgb in `apps/` or `packages/ui` (`pnpm check:hex` gates).
- Creatives render ONLY where `moderation_status=approved` (component + serve-side, NN1). Serve wire always carries `label:"sponsored"`; `<Badge variant="sponsored">` type-forbids children.
- Tracking writes ONLY to existing `ads.impressions`/`ads.clicks` partitioned tables (no new tables). Impression fires on viewport visibility only — never on render/mount.
- No HTML/script creatives (img-only v1), no third-party ad scripts, autoplay must respect `prefers-reduced-motion`, zero CLS (reserved boxes), slide 1 eager / rest lazy.
- Backend module boundary: `modules/ads` never imports other modules (import-linter). `public=True` routes must match `backend/core/public_routes.txt` (paths unchanged here, so no edit).
- Backend gates before push: `ruff format`, `ruff check`, `mypy`, `lint-imports`, pytest. Frontend: `pnpm check:hex`, `pnpm test`. Run `ruff format` at the end of every backend task (D16 lesson).
- Before push: `git pull origin dev` into the feature branch (user instruction).
- All new user-visible slots collapse gracefully (or show local house fallback) when the engine is dark/blocked.

## File Structure

- `backend/core/modules/ads/service.py` — SLOT_KEYS + `categories` targeting + optional-pincode eligibility (modify)
- `backend/core/modules/ads/router.py` — serve: optional pincode, `category`, `count`, multi-ad response (modify)
- `backend/core/modules/ads/schemas.py` — `AdServeOut.ads` (modify)
- `backend/core/scripts/seed_house_ads.py` — house campaigns/creatives/placements per milk slot (create)
- `backend/core/tests/test_ads_serve.py`, `test_ads_admin.py`, `test_dev_only_guard.py` — new tests (modify)
- `packages/ui/src/lib/sponsored.ts` + `sponsored.test.ts` — parseServeResponse, isSafeMediaUrl, serveQuery (modify)
- `packages/ui/src/lib/location.ts` (+ test) — `pincodeFromCookieHeader` (modify)
- `packages/ui/src/components/ad-image.tsx`, `sponsored-badge.tsx` — atoms (create)
- `packages/ui/src/composites/ad-slot.tsx` — AdSlot molecule + AdUnit + useImpression + sendAdBeacon (create)
- `packages/ui/src/composites/ad-carousel.tsx` — AdCarousel organism (create)
- `packages/ui/src/index.ts` — barrel exports (modify)
- `apps/web-milk/app/api/ads/[...path]/route.ts` — BFF proxy (create, copy of web-agri)
- `apps/web-milk/components/molecules/HouseAdCard.tsx` — local fallback card (create)
- `apps/web-milk/components/organisms/GlobalAdBanner.tsx` — layout-shell carousel wrapper (create)
- `apps/web-milk/app/[locale]/layout.tsx`, `page.tsx`, `p/[category]/page.tsx`, `search/page.tsx`, `directory/businesses/[slug]/page.tsx` — mounts (modify)
- `apps/web-milk/next.config.ts` — minimal CSP hardening headers (modify)
- `apps/web-admin/app/ads/ads-manager.tsx` — new slot keys + categories field + per-slot placement list (modify)
- `scripts/e2e-api.mjs` — run house seed + flag enable for e2e (modify)
- `e2e/ads-surfaces.spec.ts` — NN2/NN3 + house-ads-visible e2e (create)

---

### Task 1: Branch sync

**Files:** none (git only)

- [ ] **Step 1:** `git fetch origin` then `git checkout feat/m2-ad-surfaces` (branch exists locally at the dev tip) and `git merge --ff-only origin/dev`. Do NOT commit `.claude/settings.json` or `.worktrees/` at any point in this plan.

### Task 2: Backend — slot registry, category targeting, multi-serve

**Files:**
- Modify: `backend/core/modules/ads/service.py`, `backend/core/modules/ads/router.py`, `backend/core/modules/ads/schemas.py`
- Test: `backend/core/tests/test_ads_serve.py`, `backend/core/tests/test_ads_admin.py`

**Interfaces:**
- Produces: `GET /ads/serve?slot=&pincode?=&locale=&category?=&count?=` → `AdServeOut{ad: ServedAdOut|None, ads: list[ServedAdOut]}` (ads weighted, distinct placements, ≤count≤5; `ad == ads[0]`). `GeoTargetIn.categories: list[str]|None`. `SLOT_KEYS` gains `milk_global_header`, `milk_home_hero`, `milk_category_banner`, `milk_search_inline`, `milk_profile_footer`.
- Matching semantics: geo rungs unchanged ({} geo = everywhere; without `pincode` only geo-untargeted placements match). `categories` absent/empty = all contexts; non-empty = serve request must carry a matching `category`. Values are shape-validated only (`^[a-z0-9-]{1,40}$`) and matched by exact string against M1 schema `category` values — a new M1 category is targetable with zero code changes.

- [ ] **Step 1: Write failing tests** — append to `backend/core/tests/test_ads_serve.py` (reuse existing `api`/`ads_redis`/`tn_geo_sample` fixtures, `_enable_ads`, `_seed_ad`):

```python
async def test_milk_slot_keys_are_registered(
    api: tuple[httpx.AsyncClient, AsyncSession], tn_geo_sample: None, ads_redis: Redis
) -> None:
    client, session = api
    await _enable_ads(session)
    for slot in (
        "milk_global_header",
        "milk_home_hero",
        "milk_category_banner",
        "milk_search_inline",
        "milk_profile_footer",
    ):
        await _seed_ad(session, geo_target={}, slot_key=slot)
        r = await client.get("/ads/serve", params={"slot": slot, "pincode": COIMBATORE_PINCODE})
        assert r.status_code == 200, (slot, r.text)
        assert r.json()["ad"] is not None, slot


async def test_serve_count_returns_distinct_placements(
    api: tuple[httpx.AsyncClient, AsyncSession], tn_geo_sample: None, ads_redis: Redis
) -> None:
    client, session = api
    await _enable_ads(session)
    for _ in range(3):
        await _seed_ad(session, geo_target={}, slot_key="milk_global_header")
    r = await client.get(
        "/ads/serve",
        params={"slot": "milk_global_header", "pincode": COIMBATORE_PINCODE, "count": 5},
    )
    assert r.status_code == 200
    body = r.json()
    ids = [ad["placement_id"] for ad in body["ads"]]
    assert len(ids) == 3 and len(set(ids)) == 3
    assert body["ad"] == body["ads"][0]  # backward compat


async def test_category_targeting(
    api: tuple[httpx.AsyncClient, AsyncSession], tn_geo_sample: None, ads_redis: Redis
) -> None:
    client, session = api
    await _enable_ads(session)
    await _seed_ad(session, geo_target={"categories": ["ghee"]}, slot_key="milk_category_banner")
    hit = await client.get(
        "/ads/serve",
        params={"slot": "milk_category_banner", "pincode": COIMBATORE_PINCODE, "category": "ghee"},
    )
    assert hit.json()["ad"] is not None
    miss = await client.get(
        "/ads/serve",
        params={"slot": "milk_category_banner", "pincode": COIMBATORE_PINCODE, "category": "milk"},
    )
    assert miss.json()["ad"] is None
    no_ctx = await client.get(
        "/ads/serve", params={"slot": "milk_category_banner", "pincode": COIMBATORE_PINCODE}
    )
    assert no_ctx.json()["ad"] is None  # category-targeted needs category context


async def test_serve_without_pincode_only_untargeted_geo(
    api: tuple[httpx.AsyncClient, AsyncSession], tn_geo_sample: None, ads_redis: Redis
) -> None:
    client, session = api
    await _enable_ads(session)
    await _seed_ad(session, geo_target={"district": COIMBATORE_DISTRICT_LGD})
    r = await client.get("/ads/serve", params={"slot": "directory_browse"})
    assert r.status_code == 200 and r.json()["ad"] is None
    await _seed_ad(session, geo_target={})
    r = await client.get("/ads/serve", params={"slot": "directory_browse"})
    assert r.json()["ad"] is not None


async def test_pending_creative_never_serves_on_milk_slot(
    api: tuple[httpx.AsyncClient, AsyncSession], tn_geo_sample: None, ads_redis: Redis
) -> None:
    """NN1 on the M2 surface: unapproved/pending creative NEVER renders."""
    client, session = api
    await _enable_ads(session)
    await _seed_ad(
        session, geo_target={}, slot_key="milk_global_header", moderation_status="pending"
    )
    r = await client.get(
        "/ads/serve", params={"slot": "milk_global_header", "pincode": COIMBATORE_PINCODE, "count": 5}
    )
    assert r.status_code == 200
    assert r.json()["ad"] is None and r.json()["ads"] == []
```

And in `test_ads_admin.py`, next to the existing geo-validation tests (reuse that file's fixtures/helpers for creating a campaign):

```python
async def test_placement_categories_accepted_and_bad_shape_422(...):
    # POST /admin/ads/placements with geo_target={"categories": ["ghee", "milk-powder"]} -> 201,
    # response geo_target round-trips; {"categories": ["Bad Value!"]} -> 422.
```

(Copy the exact fixture/creation pattern already used by that file's placement tests.)

- [ ] **Step 2: Run tests, verify they fail** — `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_ads_serve.py -x -q`. Expected: new tests fail (unknown_slot 422 / missing pincode 422 / unknown geo key 422).

- [ ] **Step 3: Implement.** In `service.py`:

```python
SLOT_KEYS: frozenset[str] = frozenset(
    {
        "directory_browse",
        # M2 (naming contract {vertical}_{placement} - a future
        # theorganic_global_header is one more line here, pure config):
        "milk_global_header",
        "milk_home_hero",
        "milk_category_banner",
        "milk_search_inline",
        "milk_profile_footer",
    }
)
MAX_SERVE_COUNT = 5
_CATEGORY_RE = re.compile(r"^[a-z0-9-]{1,40}$")
_GEO_RUNGS = ("state", "district", "pincodes")
```

`GeoTargetIn` gains:

```python
    categories: list[str] | None = Field(default=None, max_length=20)

    @field_validator("categories")
    @classmethod
    def _category_shape(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        bad = [c for c in value if not _CATEGORY_RE.fullmatch(c)]
        if bad:
            raise ValueError(f"invalid categories: {bad!r}")
        return value
```

`geo_matches` — `pincode` becomes `str | None`; the "{} = everywhere" check must ignore the non-geo `categories` key:

```python
def geo_matches(
    geo_target: dict[str, Any],
    *,
    pincode: str | None,
    district_lgd: int | None,
    state_lgd: int | None,
) -> bool:
    """No geo rung declared = everywhere. Otherwise ANY declared rung matching
    the resolved chain is a hit (non-negotiable 2). An unknown viewer location
    (pincode=None) matches only geo-untargeted placements - fail closed."""
    if not any(geo_target.get(k) for k in _GEO_RUNGS):
        return True
    pincodes = geo_target.get("pincodes") or []
    if pincode is not None and pincode in pincodes:
        return True
    ...  # district/state checks unchanged
```

New pure function + `eligible_placements` changes:

```python
def category_matches(geo_target: dict[str, Any], category: str | None) -> bool:
    """M2: category-targetable inventory. Values are matched by exact string
    against the M1 schema `category` values - shape-validated only, so a new
    schema category is targetable with zero code changes here."""
    wanted = geo_target.get("categories") or []
    if not wanted:
        return True
    return category is not None and category in wanted


async def eligible_placements(
    session, *, slot_key: str, pincode: str | None, today: date, category: str | None = None
) -> list[tuple[Placement, Creative]]:
```

Inside: only resolve district/state when `pincode is not None` (else both `None`); the accept condition becomes `geo_matches(...) and category_matches(placement.geo_target, category)`.

In `schemas.py`, `AdServeOut`:

```python
class AdServeOut(BaseModel):
    ad: ServedAdOut | None       # legacy single-ad shape (web-agri D21 mount)
    ads: list[ServedAdOut] = []  # M2 carousel: weighted, distinct placements
```

In `router.py`, rewrite `serve` (signature + selection loop; extract the existing copy/media/ServedAdOut assembly into a local `_to_served(placement, creative)` helper):

```python
@router.get("/serve", public=True)
async def serve(
    request: Request,
    session: SessionDep,
    slot: str,
    pincode: Annotated[str | None, Query(min_length=6, max_length=6, pattern=r"^\d{6}$")] = None,
    locale: Literal["en", "ta", "hi"] = "en",
    category: Annotated[str | None, Query(pattern=r"^[a-z0-9-]{1,40}$")] = None,
    count: Annotated[int, Query(ge=1, le=service.MAX_SERVE_COUNT)] = 1,
) -> AdServeOut:
    await _require_flag(session)
    if slot not in service.SLOT_KEYS:
        raise HTTPException(status_code=422, detail="unknown_slot")
    now = datetime.now(UTC)
    viewer = _viewer(request, now)
    settings = get_settings()
    candidates = await service.eligible_placements(
        session, slot_key=slot, pincode=pincode, category=category, today=now.date()
    )
    pool = [
        (placement, creative)
        for placement, creative in candidates
        if await service.under_freq_cap(
            viewer, placement.id, cap=settings.ads_freq_cap_per_day, now=now
        )
    ]
    served: list[ServedAdOut] = []
    while pool and len(served) < count:
        placement, creative = service.pick_weighted(pool, _rng)
        pool = [c for c in pool if c[0].id != placement.id]
        try:
            service.validate_target_url(creative.target_url)  # re-check at serve
        except ValueError:
            continue  # a bad row must never reach a page
        await service.record_serve(viewer, placement.id, now=now)
        served.append(_to_served(placement, creative, locale=locale, base=settings.media_public_base_url))
    return AdServeOut(ad=served[0] if served else None, ads=served)
```

(Note: the freq-cap list comprehension with `await` is invalid — build `pool` with an explicit `for` loop like the existing code.)

- [ ] **Step 4: Run tests** — `pytest tests/test_ads_serve.py tests/test_ads_admin.py tests/test_ads_beacons.py -q`. Expected: ALL pass (existing tests must not regress — `pincode` stays accepted, single-ad shape intact).
- [ ] **Step 5:** `ruff format . && ruff check . && mypy . && lint-imports` (from backend/core, venv). Fix anything.
- [ ] **Step 6: Commit** — `feat(m2): milk slot keys, category targeting, multi-creative serve`

### Task 3: Backend — house-ad seed + e2e hookup

**Files:**
- Create: `backend/core/scripts/seed_house_ads.py`
- Modify: `backend/core/tests/test_dev_only_guard.py`, `scripts/e2e-api.mjs`

**Interfaces:**
- Produces: idempotent script `python scripts/seed_house_ads.py [--base-url URL] [--console-url URL] [--enable-flag]`. Per milk slot × 2 messages ("Post your need" → `{base}/post-need`, "List your business" → console listings URL), each as its own campaign+creative(approved, no media)+placement(geo `{}`, weight 1) under a house advertiser business. `--enable-flag` flips `ads_enabled` (refused when `app_env == "prod"`). Legit prod content → NO `refuse_in_prod`.
- Why campaign-per-message: `eligible_placements` serves the *newest approved creative per placement* and a placement belongs to one campaign — distinct messages must be distinct campaigns to rotate in the carousel.

- [ ] **Step 1: Write failing test** — in `test_dev_only_guard.py`, extend `test_the_guard_is_actually_wired_into_the_fixture_scripts`: add `"seed_house_ads.py"` to the NO-guard loop (`load_geo.py`, `import_vendor_seed.py`) with the reason string "house ads are first-party production content". Run: fails (file missing).
- [ ] **Step 2: Write the script** `backend/core/scripts/seed_house_ads.py`:

```python
"""House-ad fill (M2.E): first-party creatives on every milk ad slot so
surfaces are never empty. This is legitimate PRODUCTION content (unlike the
e2e fixtures) - deliberately no refuse_in_prod; see test_dev_only_guard.py.
Idempotent: keyed on campaign name; re-runs reconcile flight_end/status.

Run:
    cd backend/core
    .venv/Scripts/python.exe scripts/seed_house_ads.py [--base-url http://localhost:3000]
        [--console-url http://localhost:3002/business/listings] [--enable-flag]
"""

import argparse
import asyncio
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign, Creative, Placement
from modules.directory import service as directory_service
from modules.directory.models import Business
from settings import get_settings
from shared.db import get_sessionmaker
from shared.flags import FeatureFlag, reset_flag_cache

_HOUSE_BUSINESS = "Milk.in House"
_PINCODE = "641001"
_FLIGHT_DAYS = 3650  # effectively evergreen; re-runs extend

MILK_SLOTS = (
    "milk_global_header",
    "milk_home_hero",
    "milk_category_banner",
    "milk_search_inline",
    "milk_profile_footer",
)


def _messages(base_url: str, console_url: str) -> list[tuple[str, dict[str, dict[str, str]], str]]:
    return [
        (
            "post-need",
            {
                "en": {"title": "Post your need", "body": "Tell vendors what you need - they reply to you."},
                "ta": {"title": "உங்கள் தேவையை பதிவிடுங்கள்", "body": "விற்பனையாளர்கள் உங்களை தொடர்பு கொள்வார்கள்."},
                "hi": {"title": "अपनी ज़रूरत पोस्ट करें", "body": "विक्रेता आपको जवाब देंगे।"},
            },
            f"{base_url}/post-need",
        ),
        (
            "list-business",
            {
                "en": {"title": "List your business", "body": "Reach milk buyers near you - free listing."},
                "ta": {"title": "உங்கள் வணிகத்தைப் பதிவு செய்யுங்கள்", "body": "அருகிலுள்ள வாடிக்கையாளர்களை அடையுங்கள்."},
                "hi": {"title": "अपना व्यवसाय जोड़ें", "body": "आस-पास के ग्राहकों तक पहुंचें।"},
            },
            console_url,
        ),
    ]


async def _ensure_house_business(session: AsyncSession) -> uuid.UUID:
    """Serve-time is_servable() is fail-closed, so the house advertiser must be
    a real, active directory business. owner_user_id is NOT an FK into identity
    (module-independence contract), so a bare uuid4 owner is fine - same shape
    the ads serve tests use."""
    existing = await session.scalar(select(Business).where(Business.name == _HOUSE_BUSINESS))
    if existing is not None:
        return existing.id
    business = await directory_service.create_business(
        session,
        owner_user_id=uuid.uuid4(),
        name=_HOUSE_BUSINESS,
        type_="shop",
        primary_pincode=_PINCODE,
    )
    await session.commit()
    print(f"seed_house_ads: created house business {business.slug}")  # noqa: T201
    return business.id


async def _ensure_house_ad(
    session: AsyncSession,
    *,
    advertiser_id: uuid.UUID,
    slot_key: str,
    tag: str,
    copy: dict[str, dict[str, str]],
    target_url: str,
) -> None:
    name = f"House · {slot_key} · {tag}"
    today = date.today()
    campaign = await session.scalar(select(Campaign).where(Campaign.name == name))
    if campaign is not None:  # reconcile, don't duplicate
        campaign.status = "active"
        campaign.flight_end = today + timedelta(days=_FLIGHT_DAYS)
        await session.commit()
        return
    campaign = Campaign(
        advertiser_business_id=advertiser_id,
        name=name,
        status="active",
        flight_start=today - timedelta(days=1),
        flight_end=today + timedelta(days=_FLIGHT_DAYS),
    )
    session.add(campaign)
    await session.flush()
    session.add(
        Creative(
            campaign_id=campaign.id,
            media_keys=[],  # copy-only house card; AdSlot renders the text variant
            copy=copy,
            target_url=target_url,
            moderation_status="approved",  # first-party content, pre-approved
        )
    )
    session.add(
        Placement(campaign_id=campaign.id, slot_key=slot_key, geo_target={}, weight=1)
    )
    await session.commit()
    print(f"seed_house_ads: created {name}")  # noqa: T201


async def _enable_flag(session: AsyncSession) -> None:
    if get_settings().app_env == "prod":
        raise SystemExit("--enable-flag refused in prod: flip ads_enabled via /admin/ops/flags")
    flag = await session.get(FeatureFlag, "ads_enabled")
    if flag is None:
        raise RuntimeError("ads_enabled flag missing - run `alembic upgrade head`")
    if not flag.enabled:
        flag.enabled = True
        await session.commit()
        reset_flag_cache()
        print("seed_house_ads: ads_enabled -> true")  # noqa: T201


async def run(base_url: str, console_url: str, enable_flag: bool) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        advertiser_id = await _ensure_house_business(session)
        for slot_key in MILK_SLOTS:
            for tag, copy, target_url in _messages(base_url, console_url):
                await _ensure_house_ad(
                    session,
                    advertiser_id=advertiser_id,
                    slot_key=slot_key,
                    tag=tag,
                    copy=copy,
                    target_url=target_url,
                )
        if enable_flag:
            await _enable_flag(session)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument("--console-url", default="http://localhost:3002/business/listings")
    parser.add_argument("--enable-flag", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.base_url, args.console_url, args.enable_flag))
```

Before finalizing, check `listingsHref` in `apps/web-milk/lib/console.ts` for the real console listings path and use that as the `--console-url` default path.

- [ ] **Step 3:** Run guard test: `pytest tests/test_dev_only_guard.py -q` → passes. Run the script against local dev DB (`.venv/Scripts/python.exe scripts/seed_house_ads.py --enable-flag`), then re-run it (idempotency), then `curl "http://127.0.0.1:8000/ads/serve?slot=milk_global_header&count=5"` — if the API is running — expect 2 house ads. If local DB/API is not up, cover via the serve tests already added (geo `{}` path) and note it.
- [ ] **Step 4:** `scripts/e2e-api.mjs` — after the `seed_e2e_milk.py` block, add:

```js
// M2: house-ad fill + ads_enabled so e2e/ads-surfaces.spec.ts is
// deterministic. Idempotent (keyed on campaign name); --enable-flag is
// dev/test-only (refused in prod inside the script).
const houseAds = spawnSync(python, ["scripts/seed_house_ads.py", "--enable-flag"], {
  cwd: core,
  env,
  stdio: "inherit",
});
if (houseAds.status !== 0) process.exit(houseAds.status ?? 1);
```

- [ ] **Step 5:** `ruff format . && ruff check . && mypy . && lint-imports`; commit — `feat(m2): house-ad seed + e2e ads bootstrap`

### Task 4: packages/ui lib — serve parsing + query + cookie pincode

**Files:**
- Modify: `packages/ui/src/lib/sponsored.ts`, `packages/ui/src/lib/location.ts`, `packages/ui/src/index.ts`
- Test: `packages/ui/src/lib/sponsored.test.ts` (extend), `packages/ui/src/lib/location.test.ts` (extend or create)

**Interfaces:**
- Produces: `parseServeResponse(raw: unknown): ServedAd[]` (reads `ads`, falls back to `[ad]`; drops unlabeled/unsafe entries; filters `media_urls` through `isSafeMediaUrl`), `isSafeMediaUrl(url: string): boolean`, `serveQuery(slotKey: string, ctx?: {pincode?: string|null; category?: string|null; count?: number; locale?: string}): string`, `pincodeFromCookieHeader(header: string): string | null`. All document-free (node-tested).

- [ ] **Step 1: Failing tests** — extend `sponsored.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { isSafeMediaUrl, parseServeResponse, serveQuery } from "./sponsored";

const AD = {
  placement_id: "p1", creative_id: "c1", slot_key: "milk_global_header",
  label: "sponsored", title: "T", body: "B",
  media_urls: ["https://media.example/a.jpg"], target_url: "https://example.com/x",
};

describe("parseServeResponse", () => {
  it("reads the ads list", () => {
    expect(parseServeResponse({ ad: AD, ads: [AD, { ...AD, placement_id: "p2" }] })).toHaveLength(2);
  });
  it("falls back to the legacy single ad", () => {
    expect(parseServeResponse({ ad: AD })).toHaveLength(1);
  });
  it("NN1: drops entries without label sponsored", () => {
    expect(parseServeResponse({ ads: [{ ...AD, label: "organic" }] })).toHaveLength(0);
  });
  it("strips unsafe media urls but keeps the ad", () => {
    const [ad] = parseServeResponse({ ads: [{ ...AD, media_urls: ["javascript:alert(1)"] }] });
    expect(ad.media_urls).toHaveLength(0);
  });
  it("returns [] on garbage", () => {
    expect(parseServeResponse(null)).toHaveLength(0);
    expect(parseServeResponse({ ad: null, ads: "x" })).toHaveLength(0);
  });
});

describe("serveQuery", () => {
  it("builds slot + validated context", () => {
    const q = new URLSearchParams(
      serveQuery("milk_category_banner", { pincode: "641001", category: "ghee", count: 5 }),
    );
    expect(q.get("slot")).toBe("milk_category_banner");
    expect(q.get("pincode")).toBe("641001");
    expect(q.get("category")).toBe("ghee");
    expect(q.get("count")).toBe("5");
  });
  it("omits malformed context instead of sending it", () => {
    const q = new URLSearchParams(serveQuery("s", { pincode: "abc", category: "Bad!" }));
    expect(q.get("pincode")).toBeNull();
    expect(q.get("category")).toBeNull();
  });
});
```

And for `location.ts`: `pincodeFromCookieHeader("agri_loc=" + encodeURIComponent(JSON.stringify({p:"641001",d:null,s:null,src:"pincode"})) + "; other=1")` → `"641001"`; malformed/missing → `null`.

- [ ] **Step 2:** `pnpm --filter @agri/ui test` → new tests fail.
- [ ] **Step 3: Implement.** In `sponsored.ts`:

```ts
/** Media URLs get the same http(s)-absolute-only gate as target_url. */
export function isSafeMediaUrl(url: string): boolean {
  return isSafeTargetUrl(url);
}

/** M2 serve envelope: prefer `ads` (carousel), fall back to legacy `ad`. */
export function parseServeResponse(raw: unknown): ServedAd[] {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return [];
  const obj = raw as Record<string, unknown>;
  const list = Array.isArray(obj.ads) && obj.ads.length > 0 ? obj.ads : [obj.ad];
  const out: ServedAd[] = [];
  for (const entry of list) {
    const ad = parseServedAd(entry);
    if (ad) out.push({ ...ad, media_urls: ad.media_urls.filter(isSafeMediaUrl) });
  }
  return out;
}

const PINCODE_RE = /^\d{6}$/;
const CATEGORY_RE = /^[a-z0-9-]{1,40}$/;
const LOCALES = new Set(["en", "ta", "hi"]);

export interface AdServeContext {
  pincode?: string | null;
  category?: string | null;
  count?: number;
  locale?: string;
}

/** Query string for GET /ads/serve — malformed context is dropped client-side
 * rather than round-tripping to a 422. */
export function serveQuery(slotKey: string, ctx: AdServeContext = {}): string {
  const q = new URLSearchParams({ slot: slotKey });
  if (ctx.pincode && PINCODE_RE.test(ctx.pincode)) q.set("pincode", ctx.pincode);
  if (ctx.category && CATEGORY_RE.test(ctx.category)) q.set("category", ctx.category);
  if (ctx.count && ctx.count > 1) q.set("count", String(Math.min(ctx.count, 5)));
  if (ctx.locale && LOCALES.has(ctx.locale)) q.set("locale", ctx.locale);
  return q.toString();
}
```

In `location.ts`:

```ts
/** Pincode out of a raw Cookie header / document.cookie string. */
export function pincodeFromCookieHeader(header: string): string | null {
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    if (part.slice(0, eq).trim() !== LOC_COOKIE) continue;
    return parseLocCookie(part.slice(eq + 1).trim())?.pincode ?? null;
  }
  return null;
}
```

Barrel: add `isSafeMediaUrl, parseServeResponse, serveQuery` + `AdServeContext` type to the sponsored export lines, `pincodeFromCookieHeader` to the location export block.

- [ ] **Step 4:** `pnpm --filter @agri/ui test` → pass. Commit — `feat(m2): serve-envelope parsing, serve query builder, cookie pincode helper`

### Task 5: packages/ui atoms — AdImage + SponsoredBadge

**Files:**
- Create: `packages/ui/src/components/ad-image.tsx`, `packages/ui/src/components/sponsored-badge.tsx`
- Modify: `packages/ui/src/index.ts`

**Interfaces:**
- Produces: `AdImage({src, alt, eager?, className?})` — sanitized `<img>` only (v1: no HTML creatives); returns `null` for unsafe src. `SponsoredBadge({className?})` — always-visible label, wraps `<Badge variant="sponsored">` (children type-forbidden → label can't be overridden).

- [ ] **Step 1:** `ad-image.tsx`:

```tsx
import { cn } from "../lib/cn";
import { isSafeMediaUrl } from "../lib/sponsored";

/**
 * Atom (M2): the ONLY way ad media reaches a page - a plain sanitized <img>,
 * never HTML/script creatives (v1 contract). Unsafe URLs render nothing.
 * `eager` is for carousel slide 1 only (rural data reality: everything else
 * stays lazy).
 */
export function AdImage({
  src,
  alt,
  eager = false,
  className,
}: {
  src: string;
  alt: string;
  eager?: boolean;
  className?: string;
}) {
  if (!isSafeMediaUrl(src)) return null;
  return (
    <img
      src={src}
      alt={alt}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      draggable={false}
      className={cn("h-full w-full object-cover", className)}
    />
  );
}
```

`sponsored-badge.tsx`:

```tsx
import { Badge } from "./badge";

/**
 * Atom (M2): the always-visible ad label (UX law 5). Thin alias over
 * <Badge variant="sponsored"> - that variant type-forbids children, so the
 * "★ Sponsored" text can never be overridden or omitted.
 */
export function SponsoredBadge({ className }: { className?: string }) {
  return <Badge variant="sponsored" className={className} />;
}
```

Barrel: `export { AdImage } from "./components/ad-image";` and `export { SponsoredBadge } from "./components/sponsored-badge";`

- [ ] **Step 2:** `pnpm --filter @agri/ui test` (regression) + `pnpm check:hex`. Commit — `feat(m2): AdImage + SponsoredBadge atoms`

### Task 6: packages/ui — AdSlot molecule

**Files:**
- Create: `packages/ui/src/composites/ad-slot.tsx`
- Modify: `packages/ui/src/index.ts`

**Interfaces:**
- Produces: `AdSlot({slotKey, category?, pincode?, locale?, endpoint?="/api/ads", heightClass, className?, fallback?})` and (exported for AdCarousel) `AdUnit({ad, endpoint, eager?})`, `sendAdBeacon(url, ad)`, `useImpression(ad, endpoint)`. Behavior: reserved fixed-height box + Skeleton while loading (zero CLS); fetches ONE approved creative via `GET {endpoint}/serve`; empty/error → `fallback` if given, else collapse (`null`); impression beacon fires once per ad at ≥50% viewport visibility (IntersectionObserver — NEVER on mount); click beacon on anchor click. Pincode: explicit prop, else `document.cookie` via `pincodeFromCookieHeader`.

- [ ] **Step 1:** Write `ad-slot.tsx`:

```tsx
"use client";

/**
 * AdSlot (M2): the one ad primitive. Vertical-agnostic - a slot key + context
 * in, an approved creative out. Contracts (SPEC M2 non-negotiables):
 * - renders ONLY what /ads/serve returns (server serves approved-only; the
 *   parse layer additionally drops anything unlabeled - NN1 defense in depth)
 * - reserved fixed-height box while loading; empty -> fallback or collapse
 *   (NN3: CLS 0 empty/loading/full)
 * - impression beacon fires at >=50% viewport visibility, once, NEVER on
 *   mount (NN2); click beacon on click; both to the D21 partitioned tables
 * - sendBeacon with keepalive-fetch fallback (view-beacon.tsx precedent)
 */
import { type ReactNode, useEffect, useRef, useState } from "react";

import { AdImage } from "../components/ad-image";
import { SponsoredBadge } from "../components/sponsored-badge";
import { cn } from "../lib/cn";
import { pincodeFromCookieHeader } from "../lib/location";
import {
  type AdServeContext,
  parseServeResponse,
  type ServedAd,
  serveQuery,
} from "../lib/sponsored";

export function sendAdBeacon(url: string, ad: ServedAd): void {
  const body = JSON.stringify({
    placement_id: ad.placement_id,
    creative_id: ad.creative_id,
    slot_key: ad.slot_key,
  });
  try {
    if (navigator.sendBeacon?.(url, new Blob([body], { type: "application/json" }))) return;
  } catch {
    /* fall through to fetch */
  }
  fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => undefined);
}

/** Impression ref: fires once when >=50% of the element is in the viewport. */
export function useImpression(ad: ServedAd | null, endpoint: string) {
  const ref = useRef<HTMLAnchorElement | null>(null);
  const fired = useRef(false);
  useEffect(() => {
    fired.current = false; // new ad -> new impression lifecycle
    const el = ref.current;
    if (!ad || !el) return;
    if (typeof IntersectionObserver === "undefined") return; // never fire blind
    const io = new IntersectionObserver(
      (entries) => {
        if (fired.current) return;
        if (entries.some((e) => e.isIntersecting)) {
          fired.current = true;
          sendAdBeacon(`${endpoint}/impressions`, ad);
          io.disconnect();
        }
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ad, endpoint]);
  return ref;
}

function sameOrigin(url: string): boolean {
  try {
    return new URL(url).origin === window.location.origin;
  } catch {
    return false;
  }
}

/** One rendered creative: image variant when media exists, copy-only house
 * card otherwise. Plain text rendering everywhere (React escaping - never
 * dangerouslySetInnerHTML). */
export function AdUnit({
  ad,
  endpoint,
  eager = false,
}: {
  ad: ServedAd;
  endpoint: string;
  eager?: boolean;
}) {
  const ref = useImpression(ad, endpoint);
  const external = typeof window !== "undefined" && !sameOrigin(ad.target_url);
  return (
    <a
      ref={ref}
      href={ad.target_url}
      {...(external ? { target: "_blank", rel: "noopener nofollow sponsored" } : { rel: "nofollow sponsored" })}
      onClick={() => sendAdBeacon(`${endpoint}/clicks`, ad)}
      className="relative block h-full w-full overflow-hidden rounded-card no-underline"
      data-testid={`ad-unit-${ad.slot_key}`}
    >
      {ad.media_urls[0] ? (
        <AdImage src={ad.media_urls[0]} alt={ad.title} eager={eager} />
      ) : (
        <span className="flex h-full w-full flex-col items-center justify-center gap-0.5 border border-line bg-brand-soft px-4 text-center">
          <span className="text-[14px] font-extrabold leading-tight text-ink">{ad.title}</span>
          {ad.body ? (
            <span className="line-clamp-1 text-[12px] leading-tight text-sub">{ad.body}</span>
          ) : null}
        </span>
      )}
      <SponsoredBadge className="absolute left-2 top-2" />
    </a>
  );
}

export function AdSlot({
  slotKey,
  category,
  pincode,
  locale,
  endpoint = "/api/ads",
  heightClass,
  className,
  fallback,
}: {
  slotKey: string;
  category?: string;
  pincode?: string | null;
  locale?: string;
  endpoint?: string;
  /** Fixed-height tailwind class(es), e.g. "h-[72px] sm:h-[90px]" — the CLS
   * reservation. Required so a slot can never be added without one. */
  heightClass: string;
  className?: string;
  /** Rendered when the engine returns nothing (flag off, no fill, blocked).
   * Omit to collapse the slot entirely. */
  fallback?: ReactNode;
}) {
  const [ad, setAd] = useState<ServedAd | null>(null);
  const [state, setState] = useState<"loading" | "empty" | "ready">("loading");
  useEffect(() => {
    let cancelled = false;
    const ctx: AdServeContext = {
      pincode: pincode !== undefined ? pincode : pincodeFromCookieHeader(document.cookie),
      category,
      locale,
    };
    fetch(`${endpoint}/serve?${serveQuery(slotKey, ctx)}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: unknown) => {
        if (cancelled) return;
        const ads = data === null ? [] : parseServeResponse(data);
        if (ads[0]) {
          setAd(ads[0]);
          setState("ready");
        } else {
          setState("empty");
        }
      })
      .catch(() => {
        if (!cancelled) setState("empty");
      });
    return () => {
      cancelled = true;
    };
  }, [slotKey, category, pincode, locale, endpoint]);

  if (state === "empty" && !fallback) return null;
  return (
    <div className={cn(heightClass, "w-full")} data-testid={`ad-slot-${slotKey}`}>
      {state === "ready" && ad ? (
        <AdUnit ad={ad} endpoint={endpoint} />
      ) : state === "empty" ? (
        fallback
      ) : (
        <div className={cn(heightClass, "w-full animate-pulse rounded-card bg-ghost motion-reduce:animate-none")} aria-hidden="true" />
      )}
    </div>
  );
}
```

Barrel: `export { AdSlot, AdUnit, sendAdBeacon, useImpression } from "./composites/ad-slot";`

- [ ] **Step 2:** `pnpm --filter @agri/ui test` + typecheck via the package's lint/build task if defined (`pnpm --filter @agri/ui lint` or `tsc --noEmit` per package convention — check package.json scripts). Commit — `feat(m2): AdSlot molecule with viewport-gated impressions`

### Task 7: packages/ui — AdCarousel organism

**Files:**
- Create: `packages/ui/src/composites/ad-carousel.tsx`
- Modify: `packages/ui/src/index.ts`

**Interfaces:**
- Produces: `AdCarousel({slotKey, pincode?, locale?, endpoint?="/api/ads", heightClass, className?, fallback?})` — fetches up to 5 creatives (`count: 5`, weight/rotation server-side), horizontal scroll-snap track (native swipe on mobile), autoplay 6 s with pause-on-touch/hover/hidden-tab and NO autoplay under `prefers-reduced-motion`, slide 1 eager / rest lazy, per-slide viewport impressions (each slide is an `AdUnit`), dot indicators. Empty → fallback/collapse, same CLS contract as AdSlot.

- [ ] **Step 1:** Write `ad-carousel.tsx`:

```tsx
"use client";

/**
 * AdCarousel (M2): the global sliding head banner. Native scroll-snap does
 * the swiping (no JS gesture lib); autoplay is a 6s interval that advances
 * scrollLeft - paused on touch/hover/hidden tab, and never started when
 * prefers-reduced-motion is set (DO NOT: autoplay without reduced-motion
 * respect). Slide 1 renders its image eager, the rest lazy (rural data).
 * Impressions are per-slide and viewport-gated via AdUnit/useImpression -
 * an off-screen slide never fires (NN2).
 */
import { type ReactNode, useEffect, useRef, useState } from "react";

import { cn } from "../lib/cn";
import { pincodeFromCookieHeader } from "../lib/location";
import { parseServeResponse, type ServedAd, serveQuery } from "../lib/sponsored";

import { AdUnit } from "./ad-slot";

export const AD_CAROUSEL_MAX = 5;
export const AD_CAROUSEL_INTERVAL_MS = 6000;

export function AdCarousel({
  slotKey,
  pincode,
  locale,
  endpoint = "/api/ads",
  heightClass,
  className,
  fallback,
}: {
  slotKey: string;
  pincode?: string | null;
  locale?: string;
  endpoint?: string;
  heightClass: string;
  className?: string;
  fallback?: ReactNode;
}) {
  const [ads, setAds] = useState<ServedAd[] | null>(null); // null = loading
  const trackRef = useRef<HTMLDivElement | null>(null);
  const pausedRef = useRef(false);
  const indexRef = useRef(0);
  const [dot, setDot] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const ctx = {
      pincode: pincode !== undefined ? pincode : pincodeFromCookieHeader(document.cookie),
      locale,
      count: AD_CAROUSEL_MAX,
    };
    fetch(`${endpoint}/serve?${serveQuery(slotKey, ctx)}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: unknown) => {
        if (!cancelled) setAds(data === null ? [] : parseServeResponse(data).slice(0, AD_CAROUSEL_MAX));
      })
      .catch(() => {
        if (!cancelled) setAds([]);
      });
    return () => {
      cancelled = true;
    };
  }, [slotKey, pincode, locale, endpoint]);

  const count = ads?.length ?? 0;
  useEffect(() => {
    if (count < 2) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => {
      if (pausedRef.current || document.hidden) return;
      const track = trackRef.current;
      if (!track) return;
      indexRef.current = (indexRef.current + 1) % count;
      track.scrollTo({ left: indexRef.current * track.clientWidth, behavior: "smooth" });
    }, AD_CAROUSEL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [count]);

  if (ads !== null && count === 0 && !fallback) return null;
  return (
    <div className={cn(heightClass, "relative w-full")} data-testid={`ad-carousel-${slotKey}`}>
      {ads === null ? (
        <div
          className={cn("h-full w-full animate-pulse rounded-card bg-ghost motion-reduce:animate-none")}
          aria-hidden="true"
        />
      ) : count === 0 ? (
        fallback
      ) : (
        <>
          <div
            ref={trackRef}
            role="region"
            aria-label="Sponsored"
            onTouchStart={() => {
              pausedRef.current = true;
            }}
            onTouchEnd={() => {
              pausedRef.current = false;
            }}
            onMouseEnter={() => {
              pausedRef.current = true;
            }}
            onMouseLeave={() => {
              pausedRef.current = false;
            }}
            onScroll={(e) => {
              const el = e.currentTarget;
              const i = Math.round(el.scrollLeft / Math.max(el.clientWidth, 1));
              indexRef.current = i;
              setDot(i);
            }}
            className="flex h-full w-full snap-x snap-mandatory overflow-x-auto overscroll-x-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          >
            {ads.map((ad, i) => (
              <div key={ad.creative_id} className="h-full w-full flex-none snap-center">
                <AdUnit ad={ad} endpoint={endpoint} eager={i === 0} />
              </div>
            ))}
          </div>
          {count > 1 ? (
            <div className="pointer-events-none absolute bottom-1 left-1/2 flex -translate-x-1/2 gap-1" aria-hidden="true">
              {ads.map((ad, i) => (
                <span
                  key={ad.creative_id}
                  className={cn(
                    "h-1.5 w-1.5 rounded-pill",
                    i === dot ? "bg-ink" : "bg-line",
                  )}
                />
              ))}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
```

Barrel: `export { AdCarousel, AD_CAROUSEL_INTERVAL_MS, AD_CAROUSEL_MAX } from "./composites/ad-carousel";`

- [ ] **Step 2:** `pnpm --filter @agri/ui test` + `pnpm check:hex`. Commit — `feat(m2): AdCarousel organism (autoplay, swipe, reduced-motion)`

### Task 8: web-milk — proxy, mounts, CSP hardening

**Files:**
- Create: `apps/web-milk/app/api/ads/[...path]/route.ts` (verbatim copy of `apps/web-agri/app/api/ads/[...path]/route.ts`)
- Create: `apps/web-milk/components/molecules/HouseAdCard.tsx`
- Create: `apps/web-milk/components/organisms/GlobalAdBanner.tsx`
- Modify: `apps/web-milk/app/[locale]/layout.tsx`, `app/[locale]/page.tsx`, `app/[locale]/p/[category]/page.tsx`, `app/[locale]/search/page.tsx`, `app/[locale]/directory/businesses/[slug]/page.tsx`, `apps/web-milk/next.config.ts`

**Interfaces:**
- Consumes: `AdSlot`, `AdCarousel` from `@agri/ui`; `CONSOLE_URL`/`listingsHref` from `@/lib/console`.
- Mount map: `milk_global_header` → layout shell (ALL pages), `milk_home_hero` → home, `milk_category_banner` (context = category value) → `/p/[category]`, `milk_search_inline` → search, `milk_profile_footer` → business profile.

- [ ] **Step 1:** Copy the ads BFF proxy file (comment header included) into web-milk.
- [ ] **Step 2:** `HouseAdCard.tsx` (server-safe molecule — the local never-empty fallback; NOT sponsored-labeled: it is first-party UI, not a served ad):

```tsx
import { Link } from "@/i18n/navigation";

/**
 * Molecule (M2): local house fallback for ad slots. Rendered ONLY when the ad
 * engine returns nothing (flag off / no fill / ad-blocker) so the reserved
 * box never collapses (NN3 CLS + "surfaces never empty"). First-party CTA,
 * not a served creative - so no Sponsored badge and no tracking beacons.
 */
export function HouseAdCard({
  title,
  vern,
  href,
}: {
  title: string;
  vern?: string;
  href: string;
}) {
  const className =
    "flex h-full w-full flex-col items-center justify-center gap-0.5 rounded-card border border-line bg-brand-soft px-4 text-center no-underline";
  if (href.startsWith("http")) {
    return (
      <a href={href} className={className} data-testid="house-ad-fallback">
        <span className="text-[14px] font-extrabold leading-tight text-ink">{title}</span>
        {vern ? <span className="vern text-[12px] leading-tight text-sub">{vern}</span> : null}
      </a>
    );
  }
  return (
    <Link href={href} prefetch={false} className={className} data-testid="house-ad-fallback">
      <span className="text-[14px] font-extrabold leading-tight text-ink">{title}</span>
      {vern ? <span className="vern text-[12px] leading-tight text-sub">{vern}</span> : null}
    </Link>
  );
}
```

- [ ] **Step 3:** `GlobalAdBanner.tsx` (server component wrapper — AdCarousel is the client island):

```tsx
import { AdCarousel } from "@agri/ui";

import { HouseAdCard } from "@/components/molecules/HouseAdCard";

/**
 * Organism (M2): the global sliding head banner, mounted in the [locale]
 * layout so it renders on EVERY milk page. Sits BELOW the header (the right
 * cluster is off-limits - site-header.tsx documents the CLS trap). Fixed
 * heights reserve the box (NN3); the house fallback keeps it filled when the
 * engine is dark.
 */
export function GlobalAdBanner() {
  return (
    <div className="mx-auto w-full max-w-[720px] px-4 pt-3">
      <AdCarousel
        slotKey="milk_global_header"
        heightClass="h-[72px] sm:h-[90px]"
        fallback={
          <HouseAdCard
            title="🥛 Post your need — vendors reply to you"
            vern="என் தேவை"
            href="/post-need"
          />
        }
      />
    </div>
  );
}
```

- [ ] **Step 4: Mounts.**
  - `app/[locale]/layout.tsx`: import `GlobalAdBanner` from `@/components/organisms/GlobalAdBanner`; render `<GlobalAdBanner />` between `<SiteHeader />` and `{children}`. (No `headers()`/`cookies()` — the layout must stay static; the island reads the loc cookie client-side.)
  - `app/[locale]/page.tsx` (home): after the CategoryTileRow `<div>` block, insert:

```tsx
      <div className="mx-auto w-full max-w-[720px] px-4 pt-4">
        <AdSlot
          slotKey="milk_home_hero"
          heightClass="h-[84px]"
          fallback={
            <HouseAdCard
              title="List your dairy business"
              vern="உங்கள் வணிகத்தைப் பதிவு செய்யுங்கள்"
              href={listingsHref(CONSOLE_URL)}
            />
          }
        />
      </div>
```

with imports `import { AdSlot } from "@agri/ui";`, `import { HouseAdCard } from "@/components/molecules/HouseAdCard";`, `import { CONSOLE_URL, listingsHref } from "@/lib/console";`.
  - `app/[locale]/p/[category]/page.tsx`: after the `<h1>`/vern block, before `<ProductPincodeFinder>`:

```tsx
      <AdSlot
        slotKey="milk_category_banner"
        category={category}
        heightClass="h-[72px]"
        fallback={
          <HouseAdCard title="🥛 Post your need — vendors reply to you" vern="என் தேவை" href="/post-need" />
        }
      />
```

  - `app/[locale]/search/page.tsx`: between `<SearchForm ...>` and the results block: `<AdSlot slotKey="milk_search_inline" pincode={loc?.pincode ?? null} heightClass="h-[64px]" />` (no fallback — inline slot collapses; search is `no-store` dynamic, `loc` already in scope).
  - `app/[locale]/directory/businesses/[slug]/page.tsx`: after the ReportDialog `<div>` (still inside `<Wrap>`): `<div className="mt-6"><AdSlot slotKey="milk_profile_footer" heightClass="h-[72px]" /></div>` (no fallback — profile footer collapses).
- [ ] **Step 5:** `next.config.ts` — add a minimal CSP-hardening header (full `img-src`-scoped CSP is a documented fast-follow; a page-wide script/img policy is a cross-cutting change out of M2 scope). Merge into existing config:

```ts
  async headers() {
    // M2 threat-model hardening (creative XSS): creatives are img-only and
    // URL-sanitized in @agri/ui; this header adds the safe page-level subset
    // (no plugin content, no <base> hijack, no clickjack framing). A full
    // img-src allowlist CSP is tracked as a fast-follow - it needs the media
    // domain plumbed into frontend env first.
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "Content-Security-Policy",
            value: "object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
          },
        ],
      },
    ];
  },
```

- [ ] **Step 6:** `pnpm check:hex && pnpm --filter @agri/web-milk test` then `pnpm --filter @agri/web-milk build` (catches server/client boundary + type errors). Run the app briefly if the local API is up and eyeball `/` (banner skeleton → house ad). Commit — `feat(m2): mount ad surfaces across web-milk + CSP hardening`

### Task 9: web-admin console — slot config

**Files:**
- Modify: `apps/web-admin/app/ads/ads-manager.tsx`

**Interfaces:**
- Consumes: Task 2's `GeoTargetIn.categories`.
- Produces: console can create placements on all 6 slot keys with optional category targeting; placements tab lists all slots.

- [ ] **Step 1:** In `ads-manager.tsx`:
  - Line ~27: `const SLOT_KEYS = ["directory_browse", "milk_global_header", "milk_home_hero", "milk_category_banner", "milk_search_inline", "milk_profile_footer"] as const;` (the slot `<select>` at ~line 609 picks these up automatically).
  - `GeoTarget` interface (~line 60s): add `categories?: string[];`
  - Placement form (~line 530-580): add a `categoriesCsv` state + text input labeled "Categories (comma-separated, optional — e.g. ghee, milk-powder)"; on submit, if non-empty: `geo_target.categories = categoriesCsv.split(",").map(s => s.trim()).filter(Boolean)`.
  - `formatGeo` helper: include categories when present (e.g. `· cats: ghee, paneer`).
  - Placements list fetch (~line 816: currently `slot_key: SLOT_KEYS[0]` only): fetch per slot key with `Promise.all(SLOT_KEYS.map(...))` and merge rows (keep per-slot limit 50), or add a slot filter `<select>` above the list defaulting to "all" that does the same. Match the file's existing fetch/error style.
- [ ] **Step 2:** `pnpm --filter @agri/web-admin build` (or the repo's typecheck task) — passes. Commit — `feat(m2): console slot registry + category targeting inputs`

### Task 10: e2e spec + full gates

**Files:**
- Create: `e2e/ads-surfaces.spec.ts`
- Test commands: full backend + frontend + e2e gates

- [ ] **Step 1:** Write `e2e/ads-surfaces.spec.ts` (helpers per `e2e/helpers.ts`: `MILK`, `apiAs`, `VENDOR_PHONE`, `fixtureSlug`):

```ts
import { expect, test } from "@playwright/test";

import { MILK, VENDOR_PHONE, apiAs, fixtureSlug } from "./helpers";

/**
 * SPEC M2 non-negotiables on the live stack (house ads seeded + ads_enabled
 * flipped by scripts/e2e-api.mjs):
 * - house ads visible (DoD: every surface filled at 641001)
 * - NN2: impression beacon fires ONLY once the slot is scrolled into view
 * - NN3: CLS ~ 0 on home with the carousel live
 * (NN1 pending-never-serves is a backend test: test_ads_serve.py.)
 */

test("global banner serves a labeled house ad on home", async ({ page }) => {
  await page.goto(`${MILK}/`);
  const banner = page.getByTestId("ad-carousel-milk_global_header");
  await expect(banner).toBeVisible();
  // Served house ad carries the wire label -> badge; if the engine were dark
  // we would see the (unlabeled) local fallback instead - fail loudly then.
  await expect(banner.getByText("★ Sponsored").first()).toBeVisible({ timeout: 15_000 });
});

test("impression fires only when the slot becomes visible (NN2)", async ({ page }) => {
  const beacons: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/ads/impressions")) beacons.push(req.postData() ?? "");
  });
  const ctx = await apiAs(VENDOR_PHONE);
  const slug = await fixtureSlug(ctx);
  await page.setViewportSize({ width: 390, height: 700 });
  await page.goto(`${MILK}/directory/businesses/${slug}`);
  await expect(page.getByTestId("ad-slot-milk_profile_footer")).toBeAttached({ timeout: 15_000 });
  await page.waitForTimeout(1500); // grace: a mount-fired beacon would land here
  expect(beacons.filter((b) => b.includes("milk_profile_footer"))).toHaveLength(0);
  await page.getByTestId("ad-slot-milk_profile_footer").scrollIntoViewIfNeeded();
  await expect
    .poll(() => beacons.filter((b) => b.includes("milk_profile_footer")).length, {
      timeout: 10_000,
    })
    .toBeGreaterThan(0);
});

test("click beacon lands in D21 tracking (NN2)", async ({ page }) => {
  const ctx = await apiAs(VENDOR_PHONE);
  const slug = await fixtureSlug(ctx);
  await page.goto(`${MILK}/directory/businesses/${slug}`);
  const slot = page.getByTestId("ad-slot-milk_profile_footer");
  await slot.scrollIntoViewIfNeeded();
  await expect(slot.getByTestId("ad-unit-milk_profile_footer")).toBeVisible({ timeout: 15_000 });
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/ads/clicks")),
    slot.getByTestId("ad-unit-milk_profile_footer").click(),
  ]);
  expect(resp.status()).toBe(200);
  const body = (await resp.json()) as { status?: string };
  expect(["ok", "duplicate"]).toContain(body.status); // duplicate = 60s dedupe window on re-runs
});

test("home CLS stays ~0 with the carousel live (NN3)", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "layout-shift API is Chromium-only");
  await page.goto(`${MILK}/`);
  await page.waitForTimeout(3000); // let the carousel resolve + settle
  const cls = await page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        let total = 0;
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            const shift = entry as unknown as { value: number; hadRecentInput: boolean };
            if (!shift.hadRecentInput) total += shift.value;
          }
        }).observe({ type: "layout-shift", buffered: true });
        setTimeout(() => resolve(total), 500);
      }),
  );
  expect(cls).toBeLessThan(0.02);
});
```

- [ ] **Step 2:** Run it: `pnpm e2e -- ads-surfaces.spec.ts` (check `e2e/package.json`/root scripts for the exact filter syntax; Playwright: `npx playwright test ads-surfaces --project=desktop` from `e2e/`). Apps + API boot via the configured webServers. Fix what fails (likely: exact beacon-body slot filtering, fixture slug helper signature, timing).
- [ ] **Step 3: Full gate sweep.**
  - backend/core: `ruff format . && ruff check . && mypy . && lint-imports && python -m pytest -q -m "not slow"` (or the repo's default pytest invocation) and `python scripts/dump_public_routes.py --check`.
  - root: `pnpm check:hex && pnpm test`.
  - Lighthouse NN4: attempt `node scripts/lhci-affected.mjs` (D10 memory: Lighthouse on Windows may not run — if it doesn't, note it and rely on the CI `lighthouse` required check on the PR; home already gates perf ≥ 0.90 with the carousel live because e2e seeding isn't part of the LHCI env, the fallback card renders — either way the reserved-box design keeps CLS at 0).
- [ ] **Step 4:** Commit — `test(m2): ad-surface e2e (visibility-gated impressions, click beacon, CLS)`

### Task 11: Sync, push, PR

- [ ] **Step 1:** `git pull origin dev` (merge into `feat/m2-ad-surfaces`; resolve conflicts if any, re-run affected gates on conflict).
- [ ] **Step 2:** `git push -u origin feat/m2-ad-surfaces`.
- [ ] **Step 3:** Open PR → base `dev`, title `feat(m2): ad surfaces + global carousel`. No `gh` CLI (D01-B) — use the GitHub API via credential fill (D12/D18 precedent). Body: summary of slots, serve API extensions, house seed, NN coverage map, CSP + web-agri-migration fast-follows. End body with the Claude Code attribution line.

## Self-Review Notes

- Spec coverage: A (atoms/molecule) → Tasks 5–6; B (carousel) → Task 7; C (mounts incl. layout shell) → Task 8; D (slot registry via console/config) → Tasks 2 + 9 (registry is code-per-D21-design; console picks up keys); E (house ads) → Task 3. Non-negotiables: NN1 → Task 2 test + parse test (Task 4); NN2 → Task 10 e2e + existing beacon/partition backend tests; NN3 → reserved-height design + Task 10 CLS test; NN4 → Task 10 Step 3. Threat model: XSS → img-only AdImage + URL gates + CSP subset; click fraud → existing D21 60s dedupe + freq cap (unchanged); pending leak → serve filter + NN1 tests; ad-blocker → fallback/collapse.
- Deliberate deviations to record in the PR: (1) slot registry stays a code frozenset per the D21 v1 design — "Ops Console config" is satisfied at the placement level; (2) full img-src CSP deferred (fast-follow); (3) web-agri's mount-fired SponsoredAd impression untouched (fast-follow to migrate it to AdSlot); (4) serve gains `ads`/`count`/`category`/optional-pincode backward-compatibly.
