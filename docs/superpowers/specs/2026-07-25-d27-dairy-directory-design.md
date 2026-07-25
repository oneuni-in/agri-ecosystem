# D27 — Dairy Directory + Brand Pages + Seed: Design

Date: 2026-07-25 · Branch: `feat/d27-dairy-directory` · Sprint spec: `docs/Sprint/sprint3_D23-D32.md` (SPEC D27)

## Goal

Mount the adjacent dairy categories (vets, feed suppliers, dairy farms, cooperatives)
as pure config on the D15 directory engine, give brand businesses (Aavin/Hatsun/
Sakthi-style) a brand-shaped page with products + "shops near you", and land the
launch-critical seed: 150+ Coimbatore-region vendors/brands loaded, indexed, and
covered, with complete TA/HI strings across Milk.in.

## Owner decisions (locked in brainstorming)

1. **Claude compiles the 150+ dataset.** The repo only has D19's 15-row starter
   sample; the real sheet never arrived as an owner input. Claude researches and
   compiles 150+ real Coimbatore-region dairy-ecosystem entities from public
   knowledge into the raw-sheet format, runs the existing normalizer, and the owner
   reviews the normalized output before anything loads.
2. **Brand pages are a variant of the existing detail page.** Same URL
   (`/directory/businesses/[slug]`); when `type == "shop"` the page renders a brand
   layout. One canonical URL per entity, immutable slugs preserved, no SEO
   duplication. No `Brand` entity — brands stay `shop`-type `Business` rows.
3. **Locale switching ships in D27 — via locale-segment routing, not the cookie.**
   (Amended during planning, owner-approved 2026-07-25.) The cookie pattern would
   invoke `cookies()`/`headers()` in `i18n/request.ts` and put the whole app back on
   per-request rendering — the exact regression D23's static fix removed, on the very
   home page the Lighthouse CI gate audits. Instead web-milk moves to standard
   next-intl routing with an `app/[locale]/` segment and `localePrefix: "as-needed"`:
   `/` stays the statically rendered English page (audited URL unchanged), `/ta` and
   `/hi` are statically generated variants with hreflang alternates (indexable Tamil/
   Hindi pages), `setRequestLocale` keeps every page static, and middleware handles
   cookie-remembered locale redirects for returning users.
4. **The loader drives the real service layer** (`create_business → add_branch →
   set_coverage → assign_categories → create_product → approve`), like
   `make_business.py` / `seed_e2e_milk.py`. Validation, moderation states, and the
   D19 fat-event indexing contract come for free. Direct bulk inserts rejected.
5. **Category URLs: `/c/[category]` landing + `/[pincode]?category=` browse.**
   SEO landing per category (ISR, JSON-LD, pincode hero — the D23 home pattern);
   browse reuses the existing `/[pincode]` results page with a category filter wired
   into the existing type-filter row → `covers(pincode, category)`. The
   category×pincode static-path explosion rejected.

## Part A — Dairy categories (pure config)

- Alembic migration inserts four rows into `directory.categories` (the
  `0016_directory_v1.py` `SEED_CATEGORIES` bulk-insert pattern): `veterinarian`,
  `feed-supplier`, `dairy-farm`, `cooperative`, each with `{en, ta, hi}` names and
  `sort_order` after the existing eight. `dairy-farm` is deliberately distinct from
  the generic `farm`/`dairy` tags so browse stays precise.
- `CATEGORY_SITES` in `modules/directory/search_sync.py` gains all four slugs →
  `"milk"`, so businesses in these categories index into the milk site search
  without needing an approved milk product (the existing `dairy → milk` mechanism).
- `covers()` already accepts `category`; verify the public
  `GET /directory/covers/{pincode}` route forwards a `category` query param and add
  it if missing. No new engine, no new tables, no business-`type` enum change.

### Frontend (web-milk)

- New `app/c/[category]/page.tsx`: ISR landing per category (D23 home pattern) —
  category name/description in the active locale, JSON-LD, pincode hero that routes
  to `/[pincode]?category=<slug>`. Unknown slug → 404.
- Existing `/[pincode]` results page accepts a `category` search param, wires it
  into the existing type-filter row, and passes it through to
  `covers(pincode, category)`.

## Part B — Brand pages

### Backend

- New public endpoint `GET /directory/businesses/{slug}/nearby-branches?pincode=`:
  returns the business's branches ordered by haversine distance from the pincode
  centroid, reusing the `covers()` anchor SQL. Branches with null `lat`/`lng` fall
  back to their own pincode's centroid. Limit ~10, cursor not needed (brands have
  bounded branch counts). Public + rate-limited + validated per house rules; 404 on
  unknown slug or unlocatable pincode handled explicitly.

### Frontend (web-milk)

- `app/directory/businesses/[slug]/page.tsx` renders a brand variant when
  `business.type === "shop"`: products grid (existing
  `GET /catalog/businesses/{slug}/products`) + "shops near you" — a pincode input
  prefilled from the visitor's last-used pincode feeding the nearby-branches
  endpoint, rendering branch cards with locality + distance.
- JSON-LD extends to `Brand`/`Organization` for shop-type businesses (vendor pages
  keep `LocalBusiness`).
- Tokens only, matches `docs/design-system.md`; new public surface passes
  Lighthouse ≥ 90.

## Part C — The seed (launch-critical)

### Dataset compilation

- Claude compiles 150+ entities across the Coimbatore region (pincodes 641001+,
  Coimbatore depth only — no thin nationwide rows): Aavin parlours, Hatsun/Arokya
  and Sakthi outlets, private dairies, dairy farms, veterinary clinics, cattle-feed
  suppliers, co-op societies.
- Rules: **PII-free by construction** (no phones/emails — contact enters via the
  D16 claim flow), addresses at locality + pincode granularity, `lat`/`lng` null
  unless confidently known (`covers()` falls back to pincode centroids),
  descriptions accurate-but-generic, moderation-appropriate.
- The raw sheet runs through the existing `scripts/normalize_vendor_seed.py`
  (dedupe on `(name, primary_pincode)`, PII scan, schema/geo validation) → the four
  contract CSVs in `backend/core/data/seeds/coimbatore/`.
- **Review gate:** normalized summary + rejects presented to the owner before load.

### Contract extension

- `businesses.csv` gains `description_hi` (contract currently stops at
  `description_ta`); normalizer, README contract, starter sample, and
  `test_vendor_seed.py` updated so seeded content is genuinely 3-locale.

### Loader

- New `scripts/import_vendor_seed.py`: reads the four CSVs, validates against the
  contract, drives the real service layer, then publishes business/product
  fat-event snapshots so the D19 indexer picks everything up.
- **Idempotent on `(name, primary_pincode)`** — the normalizer's own dedupe key; a
  match means skip, no schema change needed. Re-running the loader creates zero
  duplicates (non-negotiable #4).
- `--dry-run` mode + end report: created / skipped / failed per entity.
- Seeded businesses get `owner_user_id = NULL` → claimable per D16. The plan phase
  verifies the service path supports ownerless creation; if it does not, the loader
  gets a narrow explicit path (never fake owner accounts).
- Milk vendors/brands receive products from `products.csv` (milk vertical,
  moderated → approved); vets/feed suppliers/co-ops need no products.
- Runs as the `app_rt` role like every other script (grants already shaped for it).

## Part C′ — TA/HI

- `apps/web-milk/i18n/request.ts` reads the `NEXT_LOCALE` cookie (web-id pattern);
  a compact locale switcher lands in the web-milk header.
- All new D27 strings (category names/landings, brand page, switcher) land in
  `packages/ui/src/i18n/messages/{en,ta,hi}.json` — plus any keys found missing.
- **New locale-completeness test** (vitest, `packages/ui`): recursive key-set
  equality + non-empty string values across en/ta/hi. Runs in the existing CI test
  job — non-negotiable #2 gains permanent teeth.
- **New `docs/i18n-glossary.md`**: canonical TA/HI terms (milk, vendor, dairy,
  veterinarian, feed, cooperative, …) sourced from the existing catalogs and geo
  `name_ta` data. Seeded descriptions and new strings must be glossary-consistent.

## Part D — Cross-links

- Vendor profile pages (D24) render the business's category chips linking to
  `/c/[category]` landings, so dairy service categories are reachable from vendor
  pages. Verified by a rendering test.

## Testing

- **Loader idempotency:** run twice against a test DB → identical row counts.
- **covers(641001):** seeded vendors appear (non-negotiable #1), including
  category-filtered calls for each of the four new categories.
- **Search index integration:** seeded business events actually produce Meili
  documents (the classic stale-index seam) — D19 indexer test pattern.
- **nearby-branches:** distance ordering, null-lat/lng fallback, unlocatable
  pincode, rate limit.
- **Locale completeness:** the new vitest check (fails on any missing/empty key).
- **Frontend:** brand-variant rendering test; category chip links; Lighthouse ≥ 90
  on `/c/[category]` and the brand page variant.
- Known traps to respect from memory: parallel-pytest DB isolation (D19), e2e
  port-3002 (D26), Lighthouse local floor (D23), ruff-format per task (D16).

## Out of scope

- No new engine, module, or `Business.type` enum value.
- No D63 bulk-import pipeline — `import_vendor_seed.py` is a careful one-off script.
- No nationwide seeding; Coimbatore depth only.
- No billing/premium changes; seeded businesses are all `free` tier, `unverified`.

## DoD

Seed loaded + searchable + `covers(641001)` test green · 3-locale completeness check
green in CI · brand "shops near you" accurate by pincode · import idempotent ·
PR → dev from `feat/d27-dairy-directory` · `feat(d27): dairy directory + seed`.
