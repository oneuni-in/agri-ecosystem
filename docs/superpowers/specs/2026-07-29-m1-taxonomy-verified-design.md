# M1 — Full Product Taxonomy + Verified-First + Onboarding — Design

Date: 2026-07-29 · Branch: `feat/m1-taxonomy-verified` · Spec: `docs/Sprint/sprint3.5_M1-M6_milk_monetization.md` (M1)

## Context

Milk.in ships today with a three-field milk spec schema. M1 widens it to the full dairy
taxonomy **as data**, surfaces that data on the home page, puts verified businesses at the
top of every organic listing, and opens a door to the Business Console for brands that
want in. Everything downstream in this sprint consumes M1's values: M2's
`milk_category_banner` slot takes a category as its context, M3 targets campaigns per
category, M5's wizard offers them as ad inventory. So the taxonomy has to be config that
new values can be added to, not a list anyone edits code to extend.

What already exists and is **not** rebuilt here:

- `SpecSchema` versions, append-only **by grant** — migration 0018 revokes UPDATE/DELETE on
  `directory.spec_schemas` from `app_rt`. A taxonomy change is therefore an INSERT of the
  next version, and nothing else is legal.
- `parse_fields` / `validate_specs` (`modules/directory/specs.py`), the validation contract
  every vertical rides. Products pin `schema_version` at create; reads never re-validate.
- Milk schema v1, seeded by migration 0018 itself: `milk_type` (enum, required),
  `fat_percent`, `pack_size`.
- `covers()` (`modules/directory/covers.py:135`) — distance-anchored keyset discovery,
  currently ordered `tier_rank, distance_m, id` with a 3-field cursor (D26).
- `milk_home()` (`modules/directory/milk_home.py:168`) — the D23 blend, whose filter chips
  are already schema-driven from `active_schema("milk")`.
- `GET /catalog/verticals/{vertical}/schema` (`catalog_router.py:280`) — the active field
  defs, today **private** (the D26 products console is its only consumer).
- D27's four **service** categories (`veterinarian`, `feed-supplier`, `dairy-farm`,
  `cooperative`) at `/c/[slug]`, driven by a hardcoded `apps/web-milk/lib/categories.ts`
  and selected on the pincode page via `?category=`.
- `MILK_TYPE_META` (`apps/web-milk/lib/milk.ts:52`) — the established pattern for
  presentation metadata: backend owns the value set, frontend maps key → icon with a
  documented fallback for unknown future keys.

**The product taxonomy is a different axis from D27's service taxonomy.** A dairy farm is a
kind of *business*; ghee is a kind of *product*. They are not merged, and they do not share
a URL namespace or a query parameter.

## Decisions taken in brainstorming

| # | Decision | Rejected alternative |
|---|---|---|
| 1 | Taxonomy = a `category` enum field on milk schema **v2**, with per-option i18n labels + icon key in the same `fields` JSONB | One vertical per category (13 verticals) — would widen `vertical_slug == 'milk'` in milk_home, seed import, search fat-events, product routes and D24 profiles |
| 2 | Ranking order `verified → premium → distance` | `premium → verified` — preserves the D26 paid promise but lets a paid signal outrank a trust signal in organic results |
| 3 | Category pages at `/p/[category]`, national landing + pincode finder | Merging into `/c/*` (one route, two meanings); pincode-scoped-only (13× the indexable surface) |
| 4 | Milk-home filters are **additive**: `filters`/`?type=` untouched, new `product_categories`/`?product_category=` | Replacing the milk_type chip row — breaks the D23 wire contract and `lib/milk.ts` |
| 5 | `category` required in v2, `milk_type` demoted to optional, existing products backfilled | Optional category (the 151-business seed would render empty category pages); read-time default to `'milk'` (a hardcoded literal in the query layer) |
| 6 | Seed extends existing brands; the item-4 fixtures ship as **real seed rows** | 12 new single-product businesses; test-only fixtures |
| 7 | Icon = key → emoji map with fallback, label = from the schema | SVG sprite (weight on the LCP path); emoji stored in the schema (presentation inside the data contract) |

## 1. Taxonomy — schema v2 with option metadata

### 1.1 `FieldDef` gains one optional field

```python
class OptionMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: dict[str, str]   # Translated locales; "en" required
    icon: str               # icon KEY, never a glyph

# on FieldDef:
option_meta: dict[str, OptionMeta] | None = None
```

Cross-checks added to `FieldDef._cross_checks`:

- `option_meta` is allowed on **enum fields only**.
- Every `option_meta` key must appear in `options` (no metadata for a value that cannot be
  stored).
- Each label goes through `Translated.from_dict` and must carry `en` — the same guard
  `FieldDef.label` already uses. **This is where the i18n-gap threat is closed**: a value
  cannot be published with a missing or malformed translation.

`validate_specs()` is **not touched**. `option_meta` is presentation metadata and takes no
part in validating a product write, so no product write path changes and no pinned product
is affected.

Not every option needs metadata. A field with `options` but no `option_meta` behaves
exactly as it does today — every existing schema stays valid, which is what makes this
additive rather than a migration of the schema format.

### 1.2 Migration 0029 — publish milk v2

`spec_schemas` is INSERT-only, so v2 is a new row, not an edit of v1.

| field | v2 |
|---|---|
| `category` | **new** · enum · `required=True` · `filterable` · `facet` · `group="basics"` · 13 options, each with `option_meta` |
| `milk_type` | `required` **False** · options **append** `mixed` · gains `option_meta` for cow/buffalo/mixed and the existing a2/toned/organic |
| `fat_percent` | unchanged |
| `pack_size` | unchanged |

The 13 option values are URL-safe slugs, because they *are* the route segment at
`/p/{value}`:

```
milk · ghee · paneer · milk-powder · yogurt · lassi · curd · buttermilk
cheese · butter · cream · khoa · flavoured-milk
```

Options are only ever **appended**, never removed or renamed — a pinned v1 product
referencing `cow` must keep validating and keep rendering forever.

### 1.3 Backfill, in the same migration

```sql
UPDATE directory.products
   SET specs = specs || '{"category":"milk"}'::jsonb,
       schema_version = 2
 WHERE vertical_slug = 'milk'
   AND specs->>'category' IS NULL;
```

Soft-deleted rows are included deliberately: an undeleted product must not come back
holding a spec that fails its own pinned schema. `products` is a normal table for `app_rt`
(UPDATE granted) — only `spec_schemas` carries the append-only grant.

### 1.4 The cost of demoting `milk_type`, stated plainly

A ghee product has no milk type, so `milk_type` cannot stay `required` once one vertical
holds the whole taxonomy. The consequence is that the schema no longer guarantees a milk
product declares its type.

**No runtime guard is added.** A `if category == "milk": require milk_type` check would put
a hardcoded taxonomy literal into the write path — the exact thing the spec's "NO hardcoded
lists anywhere" forbids, and the thing that would have to be edited when the taxonomy grows.
Enforcement lives where it already lives for seeded data: `normalize_vendor_seed.py`
validates every row against the real `parse_fields`/`validate_specs` contract before import.

Second-order effect, fixed here: `compute_price_banner()` currently derives the D23 price
banner and `seller_count` from every milk-vertical product. Ghee products have no
`milk_type` so they never contribute a band — but they *do* contribute to `seller_count`,
which would inflate "N sellers" under a milk-only price band. **`milk_home()` will pass only
`category == "milk"` products into `compute_price_banner()`.**

## 2. Verified-first ranking

### 2.1 `covers()`

```python
_VERIFIED_RANK = "CASE WHEN b.verification_status = 'verified' THEN 0 ELSE 1 END"
```

The enum is `unverified | pending | verified` (`modules/directory/models.py:27`). Only
`verified` ranks up — `pending` sorts with `unverified`, so **sitting in the D16 queue buys
nothing**. That is the whole answer to the fake-verification threat: the badge and the
ranking boost come from the same admin decision, and there is no second path to either.

- Order becomes `ORDER BY verified_rank, tier_rank, distance_m, b.id`.
- The cursor goes **3 → 4 fields** (`verified:tier:distance:id`). `decode_covers_cursor`
  already rejects a wrong field count with `InvalidCursorError`; in-flight D26 cursors will
  400. This is the third cursor format change (2 → 3 at D26, 3 → 4 here), it is pre-launch,
  and it is recorded rather than worked around.
- `covers()` is the only ordering site. `milk_home()` consumes `covers()` and inherits the
  new order with no change of its own — as do the D27 category browse and the D24 profile's
  nearby lists.

### 2.2 Search (D19)

The Meilisearch index already carries `verified` as a **filterable** attribute
(`modules/search/indexing.py:48`) but not a sortable one. The spec forbids a search index
rebuild, so:

**The hook is a stable partition of each returned result page by `verified`.** Order within
each partition is preserved exactly, so Meili's relevance ranking is untouched and nothing
about the index changes.

Its limitation is stated rather than hidden: this reorders *within* a page. It does not pull
a verified result on page 3 onto page 1. Sortable-attribute promotion, if it is ever wanted,
is a settings change plus a reindex — out of scope here by instruction.

## 3. Wire contract — all additive

### 3.1 The taxonomy becomes publicly readable

`GET /catalog/verticals/{vertical}/schema` moves to public (route added to
`backend/core/public_routes.txt` in the same PR, per the SecureRouter contract). It returns
admin-authored config with no PII, it is rate-limited like every other public route, and it
is already the D26 console's source. One taxonomy source read by both consumers beats a
second endpoint that can drift.

### 3.2 Milk home

```
GET /catalog/milk/home/{pincode}?type=cow&product_category=ghee
```

- New optional `product_category` query param, validated against the active schema's
  `category` options; an unknown value is treated as absent (the D27 precedent for
  unrecognised `?category=`), never a 422.
- Response gains `product_categories: list[str]` — `["all", *options]`, built the same way
  `filters` is, so it is populated in every scope branch including the empty states and the
  chip row never reflows.
- `filters`, `?type=`, and every other field are **unchanged**. `lib/milk.ts` stays
  field-for-field accurate and the D23 tests stay green.
- `MilkProductOut` gains `category: str | None`.

### 3.3 Naming, and the collision that forced it

The param is `product_category` end to end — API and frontend URL.

`?category=` on `/{city}/{pincode}` **already means D27's service taxonomy**
(`apps/web-milk/app/[locale]/[city]/[pincode]/page.tsx:143`). Reusing it would have produced
a route where `?category=ghee` and `?category=dairy-farm` silently ran different queries.

## 4. Frontend — atomic, new tree only

Per the sprint's standing rule, all new components are atomic and **nothing shipped is
retro-refactored**. `apps/web-milk` has no `components/` directory today; M1 creates it.

```
apps/web-milk/components/
  atoms/       Icon.tsx            icon key → emoji, fallback 🥛
               Label.tsx           EN line + vernacular line
  molecules/   CategoryTile.tsx    Link + Icon + Label
               ListBusinessCta.tsx
  organisms/   CategoryTileRow.tsx horizontally scrollable, server-rendered
apps/web-milk/lib/taxonomy.ts      fetchProductCategories()
```

### 4.1 Where labels and icons come from

**Labels come from the schema** (`option_meta[value].label[locale]`, falling back to `en`).
A newly added value therefore arrives already translated, or it was rejected at
admin-write time — the tile row can never ship English-only for a value that exists.

**Only the icon is mapped in the frontend**, key → emoji, with a `🥛` fallback for an
unknown key. This is the `MILK_TYPE_META` pattern, and it is what preserves the zero-code
guarantee: add `khoa` to the schema and it renders immediately with the right label and a
fallback icon; giving it its own glyph later is an optional one-line cosmetic follow-up, not
a prerequisite. Emoji also costs zero requests and zero bytes on the LCP path.

### 4.2 Fetching without a build-time dependency on the backend

```ts
// lib/taxonomy.ts
export async function fetchProductCategories(): Promise<ProductCategory[]> {
  try {
    const res = await fetch(`${API}/catalog/verticals/milk/schema`,
                            { next: { revalidate: 3600 } });
    if (!res.ok) return [];
    return categoriesFromSchema(await res.json());
  } catch { return []; }
}
```

Backend unreachable at build time ⇒ empty array ⇒ the row renders nothing and **the build
still succeeds**, self-healing at the next revalidate. A CI or Docker build must never fail
because a config endpoint was down.

### 4.3 Pages

**Home (`/[locale]/page.tsx`)** — `<CategoryTileRow>` below the pincode hero. A server
component with no client JS, no images, and no hydration island. `revalidate = 3600` and the
page's static (`○`) status are both preserved: the fetch happens at build/revalidate, not
per request.

**`/[locale]/p/[category]/page.tsx`** — mirrors D27's `/c/[category]` shape:

- `generateStaticParams` = locales × taxonomy values.
- `dynamicParams = true` — a value added to the schema *after* a deploy still renders, on
  demand. This is what makes non-negotiable 1 true in production and not just in a test.
- `revalidate = 3600`, `CollectionPage` JSON-LD, `h1` = the schema label.
- A value not in the taxonomy at request time → `notFound()`.
- The pincode finder routes to `/{city}/{pincode}?product_category={value}`.

**Pincode page** — `?product_category=` narrows the milk-home call, sets `noindex`, and
canonicalises back to `/{city}/{pincode}`. Identical to the rule D27 already applies to
`?category=`, so the thin-pincode indexing posture is unchanged.

### 4.4 The CTA, and the header risk

"List your dairy business" → `${NEXT_PUBLIC_CONSOLE_URL}/business/listings`. The Business
Console is `apps/web-agri/app/business/*` (agri.in, port 3002), so this is a cross-origin
link to the existing D16 claim/create flow. A door, not a flow — no new page, no new route,
no new backend surface. `NEXT_PUBLIC_CONSOLE_URL` is a new web-milk env var (dev default
`http://localhost:3002`), added to the app's env example and to the staging/compose env
alongside the existing `API_BASE_URL` and `APP_ORIGIN`.

Placements: header, footer, and both empty states (`tn_no_vendors`, `out_of_area`).

**The header placement is the one real Lighthouse risk, and it is a measured one.**
`apps/web-milk/app/[locale]/site-footer.tsx` records that adding a fourth item to the
header's right cluster moved CLS from 0.098 to 0.136 and delayed LCP — which is why the
data-saver toggle lives in the footer. Mitigations, in order:

1. The header CTA is a **static server-rendered link** — present in the initial HTML,
   never hydrating, so it cannot shift as the three existing islands populate.
2. It is placed outside the right cluster (which is what re-wrapped).
3. If Lighthouse still regresses, it drops to `sm:` and up. The gate is not soft-disabled
   and the threshold is not lowered.

## 5. Seed

`products.csv` gains a `category` column; every existing row becomes `milk`. The other
twelve categories hang off brands that plausibly sell them (Aavin → ghee, paneer, curd,
butter, khoa; and so on), with TA and HI on every new product name.

Two rows are shaped deliberately and ship as **real seed data**, not test scaffolding:

- a brand carrying exactly **one** product, and
- a brand carrying **all thirteen**.

These are non-negotiable 3's evidence — the "one or all" claim is proven against the same
data a visitor sees, not against a synthetic fixture.

`MILK_SPEC_FIELDS` in `backend/core/scripts/normalize_vendor_seed.py` is re-mirrored to v2.
That mirror is byte-for-byte deliberate (its own comment says so): the script validates
seed rows through the real `modules.directory.specs` contract, so a stale mirror means the
seed validates against a schema that no longer exists.

## 6. Tests — the four non-negotiables

| # | Test | What would break it |
|---|---|---|
| 1 | **add-a-schema-value**, in two halves that together prove one claim. Backend (pytest): publish v3 in-test with a new option + `option_meta`; assert it appears in the public schema payload, in `product_categories`, and is accepted as a product spec value. Frontend (component test): `CategoryTileRow` given that schema payload renders the new value with its schema label and the fallback icon. Zero source edits in the test's diff. | any hardcoded list, anywhere |
| 2 | **verified-first.** Two businesses, identical `subscription_tier`, identical distance (same `primary_pincode`, no branches) → verified first. Plus a cursor round-trip **across** the verified boundary. | the 4-field cursor — the half that fails silently |
| 3 | **one vs all.** The 1-product brand and the 13-product brand both render correctly on the D24 profile and on their category pages. | catalog assumptions about product count |
| 4 | **Lighthouse ≥ 90** on home with the tile row live. | the header CTA (§4.4) |

Test 2 covers the pending case explicitly: a `pending` business must **not** outrank an
`unverified` one, or the D16 queue becomes a ranking lever.

CI is the arbiter for test 4. The local Lighthouse floor on this machine is ~0.79–0.83 for
pages that pass at ≥0.90 in CI (recorded at D23 and again at D27); local numbers are not
evidence in either direction.

## 7. Integration surface — verified, not assumed

Each of these is checked to pick up new values with **zero code**:

| Consumer | Mechanism | Check |
|---|---|---|
| D23 filters | `product_categories` from `active_schema` | new value appears in the chip row |
| D24 profiles | products render from pinned specs | 1-product and 13-product brands (test 3) |
| D26 dashboard | product form reads `/verticals/milk/schema` | new option selectable, no code change |
| D19 search facets | `vertical` + `verified` already indexed | re-rank hook; no settings change, no reindex |
| M2/M3 (later) | `milk_category_banner` context = a category value | new value = targetable inventory automatically |

## 8. Risks accepted

1. **Cursor break.** Third format change; in-flight D26 cursors 400. Pre-launch.
2. **`milk_type` no longer required.** Schema-level guarantee traded for a single-vertical
   taxonomy; seed-time validation and the price-banner narrowing (§1.4) absorb it.
3. **Public schema route.** Config becomes scrapable. It carries no PII, is rate-limited,
   and was already readable by any authenticated vendor.
4. **Header CTA vs Lighthouse.** Measured risk with a stated fallback (§4.4).
5. **Search re-rank is page-local.** Stated, not papered over (§2.2).

## Out of scope

No new tables. No "Recommended" label anywhere — that is M3's rule and M3's ranking
function. No retro-refactor of shipped components. No search index rebuild. No rating or
response-time signal added to `covers()`: the spec's "existing relevance" is the order that
exists today (tier, then distance), and inventing a new ranking input here would be a
different feature.

## DoD

Four tests green · every category value seeded and translated (EN/TA/HI) · PR → `dev` ·
`feat(m1): dairy taxonomy + verified-first + onboarding CTA`.
