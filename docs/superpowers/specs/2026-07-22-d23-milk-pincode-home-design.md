# D23 — Pincode-First Milk Home + Empty-State Contract — Design

**Branch:** `feat/d23-milk-home` (off `dev`)
**Source spec:** `docs/Sprint/sprint3_D23-D32.md` (D23 block)
**Commit target:** `feat(d23): milk pincode home` → PR to `dev`
**Date:** 2026-07-22

---

## 1. Purpose

Milk.in's homepage *is* a pincode box. Enter a pincode → every milk option nearby (brands +
local vendors), with milk-type filters and a today's-price banner. The load-bearing feature is
the **three-way empty-state contract**: because geo is Tamil-Nadu-scoped, non-TN and
zero-coverage pincodes must render as *warm, demand-capturing features* — never error screens.

This spec is **configuration over the Sprint-2 engines** (directory/coverage/products/leads/geo).
New code exists only where it is milk-specific glue: the blend endpoint, the notify-me capture,
and the web-milk UI.

## 2. Integration surface (confirmed by research)

| Surface | What exists | Reuse |
|---|---|---|
| **covers() / D15** | `GET /directory/covers/{pincode}` (public, rate-limited, keyset cursor). Returns covering **businesses** `{id,name,slug,type,verification_status,subscription_tier,primary_pincode,distance_m}`. No product/price/milk-type data. `business.type ∈ {vendor,shop,lab,farm}`. | Discovery source. |
| **location / D19** | `GET /identity/location?pincode\|lat,lng` → `{pincode,district,state,source}`. **No `is_tn` flag** — TN-scoping is implicit: non-TN pincode → `district_for_pincode` returns None. `PATCH /identity/profile` (pincode only) is the sole location writer; non-TN → 422. `agri_loc` cookie (`LocContext`) read SSR via `parseLocCookie` from `@agri/ui`. | TN/non-TN discrimination via `shared/geo.district_for_pincode`; profile persistence; cookie prefill. |
| **products / D17** | `directory.products` with `specs` JSONB (`milk_type`, `fat_percent`, `pack_size`) + **free-text** `price_display`. Milk schema is DB-driven: `spec_schemas.fields` for `vertical_slug="milk"` v1 (`MILK_SCHEMA_V1_FIELDS`, seeded in `0018_catalog_v1.py`); `milk_type` enum = **cow/buffalo/a2/toned/organic**. `active_schema(session,"milk").fields` returns it. Product lists (`list_business_products`, `list_vertical_products`) filter only on approved+active — **no pincode or specs filter exists**. Search index **omits** `specs`. | Filter chips + price banner source. |
| **leads / D18** | `leads.inquiries` requires `business_id NOT NULL`; `route_inquiry` **422s on zero coverage**. So it **cannot** hold a notify-me record. No interest/waitlist table exists. | New lightweight interest table (below). |

**The core gap:** no query does "milk products covering pincode X, filtered by type." It must be
**composed** — decision below.

## 3. Design decisions (approved)

1. **Composition lives in a thin backend endpoint** (not the Next SSR layer, not Meili). Keeps the
   price/filter/empty-state logic where pytest coverage is strongest; SSR page is a thin renderer
   with one cacheable, rate-limited call. Read-only — no migration for the read path.
2. **Notify-me → new `leads.pincode_interest` table** (not relaxing D18 `Inquiry`, not event-only).
   Keeps D18's "one inquiry → one covering inbox" invariant intact; demand is durably queryable
   for seeding priority. Costs one new migration.
3. **Filter chips render strictly from the D17 schema + a synthetic "All."** Chips = All / Cow /
   Buffalo / A2 / Toned / Organic. Curd&Ghee (a different product) and Home-delivery (a service
   attribute, not a milk_type) are **out of D23's type axis** — deferred, not hardcoded.
4. **Vendors vs brands split** (no "brand" business type exists): `type ∈ {vendor,farm}` →
   "Local vendors"; `type == shop` → "Brands & shops nearby"; `lab` excluded from milk home.

## 4. Architecture & routes (web-milk, App Router)

- **`/`** — ISR static hero. Pincode box + GPS pill + type-filter shell + two big-CTA stubs
  (→ D24 vendor list / D25 need-posting, non-functional placeholders here). `WebSite` +
  `Organization` JSON-LD. Indexable. No per-visitor results (stays cacheable).
- **`/[pincode]`** — ISR results, `export const revalidate = 300`. Clean shareable URL
  `milk.in/641001`. 6-digit guard → `notFound()` on non-matches (static routes `/search`,
  `/api`, `/notifications` resolve first — no collision). `generateStaticParams` pre-renders a
  small popular-pincode set; the rest are on-demand ISR.
- **Type filter = `?type=cow` query param** on the pincode route (SSR reads it; client updates the
  URL). **No offset paging** — cursor keyset only, matching covers().
- **GPS "use my location"** → browser geolocation → `GET /identity/location?lat&lng` → resolved
  pincode → client-navigate to `/[pincode]`.
- **LocationPill** — extend existing `app/header-location.tsx` (never duplicate). Switching pincode
  navigates, sets `agri_loc` cookie, and `PATCH /identity/profile` when logged in (non-TN → 422 is
  swallowed into the out-of-area empty state, not surfaced as an error).

## 5. Backend: milk-home blend endpoint

`GET /catalog/milk/home/{pincode}?type=&cursor=` — **public, rate-limited, read-only**. Reuses
`covers()` + `catalog_service` + `shared/geo` (geo is shared → no cross-module import violation).

**Server-computed 3-way discriminator:**

| `scope` | condition | empty-state |
|---|---|---|
| `out_of_area` | `district_for_pincode(pincode)` → None (non-TN / unlisted) | (c) |
| `tn_no_vendors` | TN district resolves, covers() returns no covering business with milk products | (b) |
| `covered` | TN + ≥1 covering business with ≥1 milk product | (a) |

**Response shape:**

```
MilkHomeOut {
  scope:        "covered" | "tn_no_vendors" | "out_of_area"
  location:     { pincode, district, state } | null      # from shared/geo; null when out_of_area
  filters:      [ { key: "all"|<milk_type>, label: {en,ta,hi} } ]   # from active_schema("milk")
  price_banner: { lines: [ {milk_type, low, high, unit} ], seller_count } | null
  vendors:      [ MilkCard ]   # business.type ∈ {vendor,farm}
  brands:       [ MilkCard ]   # business.type == shop
  next_cursor:  string | null
}
MilkCard { id, name, slug, type, verification_status, subscription_tier, distance_m,
           products: [ {milk_type, fat_percent, pack_size, price_display} ] }
```

`filters` is schema-driven (non-negotiable #2) and the banner is computed (non-negotiable #4) —
both are therefore unit-testable in pytest. Icons/emoji per `milk_type` are a **cosmetic frontend
map**, not part of the filter set; vernacular comes from the schema `label.{ta,hi}`.

**Composition steps (server-side):**
1. `district_for_pincode(pincode)` → None ⇒ `out_of_area`, return early with `location:null`,
   empty results, still return `filters` (schema-driven, pincode-independent).
2. `covers(session, pincode=…, cursor=…, limit=…)` → covering businesses (keyset-paginated).
3. For those businesses, load approved+active milk products; drop businesses with none.
   Empty ⇒ `tn_no_vendors`.
4. Split by `type`; attach each business's milk products (filtered by `?type=` when present).
5. Compute the price banner (below); set `scope = covered`.

**Filtered-empty edge case:** `covered` scope but `?type=cow` matches nothing → still `covered`;
frontend shows a *light inline* "No cow milk listed here yet — see All", **not** the warm district
card. Scope reflects **unfiltered** coverage.

## 6. Price banner computation

`price_display` is **free text** (`"₹55/L cow · ₹110/L A2"`), not numeric. The endpoint:
- regex-extracts `₹\s*(\d+)` tokens per product,
- groups by that product's `specs.milk_type`,
- takes min/max per type → `"Cow ₹52–60/L"`,
- `seller_count` = distinct covering businesses with ≥1 milk product.

Products whose `price_display` yields no parseable number are **skipped from the banner**
(best-effort, documented). Banner is genuinely "from real listings" (non-negotiable #4).

## 7. Empty states (warm, never errors)

- **(a) covered:** type filters → price banner → Local vendors → Brands & shops.
- **(b) tn_no_vendors:** warm card — "No milk vendors in **{district} ({pincode})** yet — notify me
  / list your dairy." Notify-me → `pincode_interest`. "List your dairy" → D24 stub link.
- **(c) out_of_area:** "We're live in **Tamil Nadu** right now — more areas coming soon" + notify-me.
  No district named (geo didn't resolve it).

All three styled with brand tokens (milk blue), never the error/alert palette. CLS=0 skeletons.

## 8. Notify-me capture

**New table** `leads.pincode_interest`:

| column | type | notes |
|---|---|---|
| `id` | UUID (v7) | PK |
| `pincode` | text | `^\d{6}$` |
| `district` | text \| null | derived when TN; null for out_of_area |
| `contact` | text \| null | optional phone/email for anon submitters |
| `from_user_id` | UUID \| null | attributed when authed |
| `milk_type` | text \| null | optional interest hint |
| `created_at` | timestamptz | default now |

**Endpoint** `POST /leads/pincode-interest` — public, `optional_auth`, rate-limited, body
`{pincode: ^\d{6}$, contact?, milk_type?}`. Attributes `from_user_id` when a session is present,
else NULL. Emits a D12 notify/audit event (`pincode_interest.created`) for seeding-priority
dashboards. Grants per module pattern (`app_rt` INSERT; admin READ).

**Migration:** one new revision, next in the committed chain (filename == internal revision),
chain-verified. This is the spec's anticipated "if any [migration], chain-verify" case.

## 9. Components (design-system exact)

- **`PincodeInput`** (`.pinbox`) → `@agri/ui` — pincode is universal across all three sites.
  White 16px container, 18px/700 numeric input (.15em tracking), solid brand "Find" button; GPS
  pill beneath (`rgba(255,255,255,.16)` bg, white border .35).
- **`TypeFilterRow`** (`.tf`) → web-milk local (milk-specific). Horizontally scrollable 86px-min
  chips, 2px border, icon+label(+vernacular); active = brand border + brand-soft bg. Renders from
  `filters`.
- **`ListingCard`** (`.card.lc`) + badges + Call/WA (`.abtn`) → reuse `@agri/ui`. Call/WA lead every
  card; forms never do (UX law #4).
- Tokens only (milk brand blue `#2563A8` via `theme-milk`); `pnpm check:hex` clean; skeletons
  reserve final dimensions (CLS=0).

## 10. SEO

- **`/`** — `buildMetadata` (canonical `https://milk.in`), `WebSite` + `Organization` JSON-LD.
- **`/[pincode]`** — `buildMetadata` (canonical `https://milk.in/{pincode}`, title
  "Milk in {district} ({pincode})"), `CollectionPage` + `ItemList(LocalBusiness)` JSON-LD.
  `noIndex` when `scope != covered` (reuse `shouldNoIndex` thin-page guard) so empty pincodes
  aren't indexed as thin pages.
- **`app/sitemap.ts`** (net-new) — home + covered pincodes. Full pincode-landing detail lands D28.

## 11. Threat model

- **Pincode-enumeration scraping:** covers() and the milk-home endpoint are keyset-only (no offset
  to walk) + rate-limited (60/60s per IP+path, shared bucket across pincodes). TN geo set (~2k
  pincodes) bounds the enumerable space.
- **Empty-state as info leak:** only public directory data is shown; no contact PII (reveal stays
  the separate login-gated, daily-capped endpoint). Notify-me stores only what the submitter
  provides.
- **Input validation:** `^\d{6}$` enforced at the FastAPI layer on every pincode surface (422
  before DB work).

## 12. Testing & DoD

**pytest (backend):**
- milk-home `641001` (seeded vendor + milk products) → `scope=covered`, vendors non-empty, banner
  computed, `filters == active_schema("milk")` options (+All).
- milk-home TN pincode with a coverage gap → `scope=tn_no_vendors`, empty results, `location.district`
  present.
- milk-home `110001` (non-TN) → `scope=out_of_area`, `location=null`.
- price-banner computation from fixture `price_display` strings (min/max grouping, unparseable skip).
- `POST /leads/pincode-interest` — anon + authed row creation, rate-limit, 422 on bad pincode.

**E2E Playwright (`e2e/milk-home.spec.ts`, :3000)** — DoD non-negotiable #1, the three branches
render correctly: `/641001` (results), a TN no-vendor pincode (warm district card + notify-me),
`/110001` (out-of-area copy + notify-me). Extends the D22 business seed helper to add a milk vendor
+ products covering 641001, and guarantees a TN pincode present in geo with a coverage gap.

**Lighthouse ≥90** on `/` and one `/[pincode]` via the existing CI gate.

**DoD:** three empty-state tests green · Lighthouse ≥90 · PR → dev · `feat(d23): milk pincode home`.

## 13. Explicit non-goals (D23 boundary)

- No vendor profile/detail pages (D24) — big-CTA + "list your dairy" are stubs.
- No need-posting / voice (D25).
- No hardcoded milk types (schema-driven only).
- No offset paging on results.
- No full sitemap enrichment (D28).
- Empty states are features, never error screens.
