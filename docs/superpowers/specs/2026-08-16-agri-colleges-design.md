# Agri colleges — education vertical (design)

**Status:** approved in brainstorming 16 Aug 2026 · owner-directed · pre-launch
**Blueprint:** new vertical, not present in v7's 36-tile registry — inserted into Block 5 (Agri.in hub)
**Branch:** `feat/agri-d41-colleges` (data track) · integration branch cut at D54
**Module:** `backend/core/modules/education/` (new) · schema `education`
**Surfaces:** `apps/web-agri` — `/colleges`, `/scholarships`, `/exams`, `/guides`

---

## 1. Decision record

**D1 — reference dataset, not a directory listing.** Colleges are information, not
businesses. No owner, no claim flow, no reviews, no leads, no logins. They get their own
module rather than riding `directory.businesses`, because every Business-shaped affordance
(claim, review, contact-reveal, subscription tier) would have to be actively suppressed on
every surface, and one missed guard puts a "Claim this business" button on a government
college.

**D2 — corpus is national breadth + Tamil Nadu depth.** Every degree-awarding agricultural
institution in India at summary depth; Tamil Nadu carried to full depth (courses, intake,
fees, admission route). Mirrors how milk.in and agri.in launched geographically.

**D3 — two-tier trust, visible on the page.** `verified` rows are human-checked against an
official source and carry `source_url` + `last_verified_at`. `listed` rows come from an
official bulk list and are unchecked. This is what makes "all colleges across India" a true
statement on day one instead of an aspiration.

**D4 — PR-seeded now, admin CRUD later.** Data lives in the repo as versioned CSV seed
bundles loaded by an idempotent import script. Provenance is git history. Tables and the
loader are shaped so a CRUD surface can be added later with no data migration.

**D5 — collection runs in parallel; integration lands after D53.** The long pole is data
verification, not code, and data collection touches no module that A-U2/A-U3/A-U4 touch.
Collection proceeds from D41 as data-only PRs with **no migration and no app code**, so
there is no alembic revision to rebase for twelve days and nothing the parallel A-U2
session can collide with.

**D6 — launch moves D57 → D61.** Owner-directed: the vertical ships *before* the agri
launch, not after. Four days are inserted after D53. Cascade: milk corrections D62–66
(the Razorpay sign-off clock moves with it), TheOrganic.in D67–78.

**D7 — no perf carve-out.** Per the A-U1→A-U4 plan's Decision 3, every agri route ships
against the 0.90 throttled-3G Lighthouse merge gate. The colleges routes are no exception.

**D8 — full-India states pulled forward into `geo`.** *(added 16 Aug 2026 during planning)*
`geo.states` shipped TN-only (D03); full-India geo was scheduled for D65 — after launch.
A national corpus cannot FK into a one-row table, so all 28 states + 8 UTs load now from
the LGD source already documented in `data/geo/SOURCES.md` (stable `lgd_code`s, no new
provenance to establish). **Districts stay TN-only until D65** and `district_id` remains
nullable. This is additive and safe: every existing consumer (`ads`, `directory.milk_home`,
`directory.search_sync`, `identity.location_router`, `identity.profile_service`) resolves a
state *from* a district or pincode, and nothing in the codebase enumerates all states.

---

## 2. Scope

### In scope (all of it ships before launch)

| Layer | Content |
|---|---|
| Colleges — Tier 1 | ~125 `verified`: central + state agricultural universities, ICAR deemed universities, ICAR research institutes, and Tamil Nadu colleges at full depth |
| Colleges — Tier 2 | `listed` national breadth: constituent and affiliated colleges from each university's own published list, topped up from AISHE |
| Courses | Canonical `programmes` catalog + per-institution intake/fees/admission route |
| Scholarships | Indian agri scholarships — ICAR, national merit, state, category-based |
| Exams | Entrance (ICAR AIEEA/JRF/SRF, CUET-UG, state entrance) **and** recruitment (IBPS AFO, NABARD Grade A, FCI, state agriculture officer) |
| Counselling | Round-wise process guides — ICAR/CUET counselling, Tamil Nadu and major state authorities |
| Foreign studies | Agricultural universities abroad, country guides, language/aptitude tests, international scholarships |

### Deferred (named, not dropped)

- Browse-by-course page tree — `programmes` data exists, so this is a page build later.
- Admin CRUD surface — tables and loader are shaped for it (D4).
- Maps on detail pages — a MapLibre bundle on every college page against a throttled-3G
  0.90 floor, for a static address. Address block + directions link out instead.
- College logos — third-party marks with unclear licensing on a commercial site, and they
  would land as the LCP element on every detail page. Typographic monogram tiles instead.
- Ads on colleges routes — M6 portability means agri slots are a config recipe, not code.
- Coins hooks, AI/RAG over the colleges corpus — A-U4 owns both; feeding the assistant a
  new corpus needs its own sign-off.
- Student accounts, saved colleges, compare tool.

---

## 3. Schedule

| Days | Work | Launch impact |
|---|---|---|
| D41–D53 | Data collection track — data-only PRs, no migration, no app code | none (parallel) |
| D54–D57 *(inserted)* | Integration: engine, import, surfaces, search indexing, registry flip | +4 days |
| D58 | Full hub QA — colleges included in the sweep | — |
| D59 | Adversarial hub audit — colleges included | — |
| D60 | Launch prep + restore drill #3 | — |
| **D61** | 🌾 Agri.in launch (was D57) | — |

Colleges is inserted **before** QA/audit/drill deliberately. Slotting it after would put an
unaudited surface into the cutover.

---

## 4. Data model

Schema `education`. All tables: UUIDv7 PK (ADR-0003), `TimestampMixin`, immutable slugs
(ADR-0006). All list endpoints cursor-paginated (ADR-0004).

### `institutions`

| Column | Notes |
|---|---|
| `slug` | immutable, unique, reserved-segment guard (see §6) |
| `name` | `TranslatedString` — EN required |
| `short_name` | `TNAU`, `IARI` |
| `kind` | enum: `central_agri_university`, `state_agri_university`, `deemed_university`, `icar_institute`, `private_university`, `affiliated_college`, `constituent_college`, `foreign_university` |
| `is_government` | bool — the single most-used student filter, explicit rather than derived |
| `parent_id` | self-FK, nullable — a constituent college points at its university |
| `country_code` | ISO-3166-1 alpha-2, default `IN` |
| `state_id` / `district_id` | FK into `geo.states` / `geo.districts`, **nullable** (null for non-`IN`) |
| `pincode`, `lat`, `lng`, `address`, `website`, `contact` | contact is jsonb |
| `established_year` | int, nullable |
| `accreditation` | jsonb — `{"icar": {...}, "naac": {"grade": "A++"}}` |
| `trust` | enum: `verified`, `listed` |
| `status` | enum: `active`, `closed`, `merged` |
| `merged_into_id` | self-FK, nullable — drives the 301 (see §7) |
| `source_url`, `last_verified_at` | |

Foreign universities are the *same entity shape* as Indian ones — foreign studies is a
filter (`country_code != 'IN'`), not a separate subsystem.

`geo` is shared machinery (`shared/geo/models.py`), not another module's tables, so FKs
into it do not breach the module independence contract. `market_data` already does this.

### `programmes`

Canonical course catalog, ~40 rows, registry-as-data.
`slug` · `name` TranslatedString · `level` enum (`diploma`, `ug`, `pg`, `phd`) ·
`discipline` enum (`agriculture`, `horticulture`, `forestry`, `fisheries`, `dairy_tech`,
`agri_engineering`, `agri_business`, `veterinary`) · `duration_months` · `description`
TranslatedString.

### `institution_programmes`

Unique on `(institution_id, programme_id)`.
`intake_seats` · `annual_fees_inr` Numeric · `fee_note` · `admission_route` ·
**`source_url` + `last_verified_at` of its own.**

Per-row stamps here are deliberate: a college's *existence* and its *current fee* go stale
at completely different rates. A single stamp on the institution would let a
verified-in-March college render a fee from two years ago under a green badge. Separate
stamps let the page say "college verified Mar 2026 · fees last checked Aug 2025".

### `student_resources`

One table for scholarships and exams — they share every structural field.
`slug` · `name` TranslatedString · `kind` enum (`scholarship`, `exam`) · `category` enum
(`entrance`, `recruitment`, `language_test`) · `scope` enum (`india`, `international`) ·
`provider` · `levels` text[] — the study levels the resource applies to, drawn from the
`programmes.level` enum (comma-separated in CSV) · `eligibility` TranslatedString ·
`benefit` · `applies_to` jsonb ·
`window` jsonb (`{opens, closes, session}`) · `official_url` · `last_verified_at` ·
`status` enum (`active`, `archived`).

### `guides`

`slug` · `title` TranslatedString · `kind` enum (`counselling`, `foreign_study`, `general`)
· `country_code` nullable · `state_id` nullable · `summary` TranslatedString · `steps` jsonb
(ordered, each `{title, body, links}`) · `official_links` jsonb · `last_verified_at` ·
`status` enum (`draft`, `published`).

Guides live in `education`, **not** in A-U3's E6 knowledge CMS. Cross-module table reads
are forbidden by the independence contract, and E6 is not shaped for round-wise counselling
steps. The content-surface overlap is real and is noted here rather than hidden; if E6
later grows a generic structured-guide type, migrating is a data move.

### Grants

`app_rt` gets **SELECT only** on all five tables. The application cannot write college data;
the import script runs under the migration role. This is both a security property and the
cleanest expression of D4 — enabling CRUD later is an explicit, reviewable grant change.

---

## 5. Public API

SecureRouter, `public=True`, `backend/core/public_routes.txt` updated in the same PR,
rate-limited, cursor-paginated.

```
GET /education/institutions        ?state= &district= &kind= &is_government= &programme=
                                   &country= &trust= &q= &cursor= &limit=
GET /education/institutions/{slug}
GET /education/programmes
GET /education/student-resources   ?kind= &category= &scope=
GET /education/student-resources/{slug}
GET /education/guides              ?kind= &country= &state=
GET /education/guides/{slug}
```

---

## 6. Public surfaces

| Route | Rendering | Indexed |
|---|---|---|
| `/colleges` | dynamic (reads `searchParams`, server-side query) | yes |
| `/colleges/state/[state]` | ISR, generated from `geo.states` | yes |
| `/colleges/abroad` + `/colleges/abroad/[country]` | ISR | yes |
| `/colleges/[slug]` | ISR | **only if `trust=verified`** |
| `/scholarships`, `/scholarships/[slug]` | ISR | yes |
| `/exams`, `/exams/[slug]` | ISR | yes |
| `/counselling` | ISR — index of `kind=counselling` guides | yes |
| `/study-abroad` | ISR — index of `kind=foreign_study` guides | yes |
| `/guides/[slug]` | ISR — canonical detail for every guide kind | published only |

`/c/agri-colleges` gains a `LIVE_ROUTES` entry → `/colleges`.

**Filtering is server-side**, breaking the `/categories` precedent. That page serializes the
whole registry and filters client-side — correct for 36 rows, wrong for hundreds to
thousands. SEO value is recovered by the ISR state pages (~35, generated from `geo.states`),
which are what rank for "agriculture colleges in Tamil Nadu" — the query the TN-depth corpus
exists to answer.

**Reserved-slug guard.** The static `state` and `abroad` segments sit beside `[slug]`. Any
institution slugifying to a reserved segment is rejected by the seed contract, not
silently shadowed.

**Trust is visible.** Verified pages carry "Verified · source · Mar 2026". `listed` pages
open with an honest notice that the entry came from an official bulk list and has not been
checked, render **no fees and no seats**, and are `noindex`. A `listed` page never shows a
number a student could act on.

**JSON-LD.** `CollegeOrUniversity` + `PostalAddress` + `BreadcrumbList` on verified pages
only. Scholarships/exams get plain `WebPage` — there is no honest schema.org type for a
scholarship, and marking one up as something it is not invites a manual action.

**i18n.** Own `ui.colleges` namespace using the per-route provider pattern (commit
`aca727a`), so college messages never enter the home's flight payload. **Institution names
render EN-only** — they are proper nouns, and TA/HI appear only where the institution itself
publishes them. UI chrome, eligibility, guide bodies and scholarship copy get EN/TA/HI.

**Sitemap.** Verified institutions, state pages, published guides, scholarships and exams
join the agri sitemap feed (D28 coverage-pincodes pattern). `listed` entries never enter it.

**Registry.** New row: slug `agri-colleges`, group `community`, order 5 (after `experts`),
icon 🏫, `soon: true` on arrival, flipped false at the end of integration. Tamil and Hindi
names flagged for owner review in the PR, as 0037 did.

---

## 7. Failure behaviour

- **F1 rule throughout** — a dead `education` engine never 500s a page. The section is
  absent or shows its empty state.
- Unknown slug → real 404, never a soft page.
- `status=merged` → **301 to `merged_into_id`**. Incoming links to renamed institutions are
  exactly the traffic worth keeping.
- `status=closed` → renders informatively with a prominent closed banner, `noindex`,
  HTTP 200, **no admission data**. A dead page still saying "apply here" is the harmful case.
- Guide with `status=draft` → 404 on the public route.

---

## 8. Data collection track (D41–D53)

Produces validated CSV bundles under `backend/core/data/seeds/education/`. **No migration,
no app code, no touching agri surfaces.** Checked by a standalone validator script with no
DB dependency, so the track has zero conflict surface with A-U2/A-U3/A-U4.

### The sourcing rule

**No row is authored from model memory.** Knowledge cutoff is May 2026; fees, intake and
counselling dates change annually, and a plausible-looking invented intake number is
precisely the harm the honesty rule exists to prevent. Every row is fetched from an official
page and that URL goes in the row.

### Sources

| Tier | Sources |
|---|---|
| Tier 1 `verified` | ICAR accreditation listing · UGC recognized-university list · each institution's own site · TNAU affiliated/constituent college listings for TN depth |
| Tier 2 `listed` | each university's own published college list · AISHE |
| Resources | ICAR, NTA, state counselling authorities, scheme portals, official exam bodies |
| Foreign | each foreign university's own site · official national study portals |

### Frozen CSV contract

Files: `institutions.csv`, `programmes.csv`, `institution_programmes.csv`,
`student_resources.csv`, `guides.csv`. UTF-8, header row required, `TranslatedString`
flattened to `_en` / `_ta` / `_hi` columns, jsonb columns carry compact JSON, dates ISO-8601
(`YYYY-MM-DD`), booleans `true`/`false`, empty cell = NULL.

**`institutions.csv`**
`slug, name_en, name_ta, name_hi, short_name, kind, is_government, parent_slug,
country_code, state, district, pincode, lat, lng, address, website, contact_phone,
contact_email, established_year, accreditation_json, trust, status, merged_into_slug,
source_url, last_verified_at`

**`programmes.csv`**
`slug, name_en, name_ta, name_hi, level, discipline, duration_months, description_en,
description_ta, description_hi`

**`institution_programmes.csv`**
`institution_slug, programme_slug, intake_seats, annual_fees_inr, fee_note,
admission_route, source_url, last_verified_at`

**`student_resources.csv`**
`slug, name_en, name_ta, name_hi, kind, category, scope, provider, levels, eligibility_en,
eligibility_ta, eligibility_hi, benefit, applies_to_json, window_json, official_url,
last_verified_at, status`

(`levels` is comma-separated, e.g. `ug,pg`.)

**`guides.csv`**
`slug, title_en, title_ta, title_hi, kind, country_code, state, summary_en, summary_ta,
summary_hi, steps_json, official_links_json, last_verified_at, status`

`parent_slug`, `merged_into_slug`, `institution_slug`, `programme_slug` and `state` /
`district` names are resolved to IDs at import.

### Contract rules (whole-bundle rejection)

`SeedContractError` rejects the **entire bundle — nothing imported** — on any of:

1. Missing `source_url` or `last_verified_at` on any row.
2. `trust=verified` without both. *(Subsumed by rule 1 in the implementation —
   `listed` rows must also cite the bulk list they came from, so rule 1 applies to every
   row. The number is kept for traceability; there is no separate branch.)*
3. `last_verified_at` not ISO-8601, or in the future.
4. `state` that does not resolve in `geo.states` (when `country_code = IN`) — national
   after D8. `district` is validated **only when supplied and its state's districts are
   loaded** (Tamil Nadu today); a district for a state whose districts have not loaded is
   rejected rather than silently dropped.
5. `country_code = IN` with an empty `state`.
6. A slug that slugifies to a reserved segment (`state`, `abroad`).
7. Duplicate slug within a file.
8. `parent_slug` / `merged_into_slug` / `institution_slug` / `programme_slug` naming a row
   that does not exist.
9. `status=merged` without `merged_into_slug`.
10. **Any fee, intake or admission-route value on a row whose institution is `listed`.**
11. Enum value outside the declared set.
12. `country_code != IN` on a row whose `kind` is not `foreign_university`.

Rule 10 is the one that makes the deadline safe: unverified breadth physically cannot carry
actionable numbers.

### The safety valve

Full-scope verified data at this volume in twelve days is ambitious. The tiering is what
makes the date safe rather than the scope: anything not verified in time ships as `listed`
— indexed in listings, no fees, no seats, noindexed detail — and any guide not finished
stays `draft` and does not render. **The launch never waits on a row, and it never ships an
invented one.**

---

## 9. Import pipeline (D54+)

`modules/education/seed_import.py` + `scripts/import_education_seed.py`, mirroring D27's
proven `import_vendor_seed` loader:

- `--dry-run` validates and reports, then rolls back.
- Idempotent: reruns match on slug and update rather than duplicate.
- Publishes fat-event snapshots after commit so the D19 search worker indexes institutions.
  `scripts/reindex_search.py` is the recovery path. Integration lands after A-U4, so
  federated hub search already exists and colleges belong in it from day one.
- `scripts/education_freshness.py` (dev-only): prints rows whose stamps have aged past a
  threshold. No worker, no UI state, no alerting — just what needs rechecking before launch.

---

## 10. Testing and gates

- **Module tests:** route contracts, every filter, cursor pagination, grant enforcement
  (app_rt cannot write), 301 on merged, 404 on draft guide, noindex on `listed`.
- **Seed contract tests:** one fixture bundle per rule in §8, each asserting whole-bundle
  rejection.
- **E2E:** Playwright specs for `/colleges` filtering, state pages, verified vs `listed`
  detail rendering, guides, and the registry tile.
- **Lighthouse:** the new routes join the **0.90 throttled-3G** merge gate, a11y and SEO at
  100. No carve-out (D7).
- **Acceptance checklist:** rows added to `docs/qa/agri-acceptance-checklist.md` *per
  checkpoint*, never reconstructed at the end.

### Known assertions to move

`backend/core/tests/test_geo.py:24` asserts `counts.states == 1`. D8 makes that 36. The
assertion is **moved, not weakened**: it compares the loaded count against the row count of
`data/geo/states.csv`, which is what it was actually trying to prove.


`e2e/agri-categories.spec.ts:46` hardcodes `expect(slugs.length).toBe(36)`, and `AG-A13` in
the acceptance checklist repeats it. A 37th tile breaks that spec. Per the standing rule the
assertion is **moved, not weakened**: it becomes a comparison against the live registry
count, which is what `AG-A2` already wanted. v7's "36-tile registry grid" copy needs the
same edit.

---

## 11. Owner actions / open items

1. **Confirm the launch slip** — D57 → D61, cascading milk to D62–66 and organic to D67–78.
   The Razorpay KYC clock moves with the milk sign-off.
2. **Review Tamil/Hindi registry names** for `agri-colleges` in the integration PR.
3. **Confirm the exams reading** — this spec covers *both* entrance and recruitment exams
   (IBPS AFO, NABARD Grade A, FCI, state agriculture officer). Assumption stated in
   brainstorming, not blocked on.
4. **Spot-check a sample of Tier-1 verified rows** against their `source_url` before the
   integration PR merges.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Verification volume misses D53 | Tiering — unverified rows ship `listed`, never invented (§8 safety valve) |
| Counselling dates go stale and mislead | `last_verified_at` on every guide; freshness script before launch; dates presented with their stamp |
| Launch slip cascades into the Razorpay clock | Stated explicitly as owner action 1 |
| Alembic revision collision with A-U2/A-U3/A-U4 | Collection track ships no migration; integration branch rebases at D54 |
| Foreign-university data thin or unverifiable | `country_code` filter means foreign studies degrades to guides only, with no broken surface |
