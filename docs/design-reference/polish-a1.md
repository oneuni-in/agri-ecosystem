# A1 — agri.in home: binding proofs & gap ledger (A-U1)

Sibling of `polish-u1.md` (milk's). Truth: `agri/agri_home_desktop_v1.html`
(A1 FINAL v4). "Wired" is DEMONSTRATED here — every bound section gets a
proof row (binding chain now; screenshots land with the CP3 capture set
under `docs/design-reference/a1/`). Sections whose engines have no data
render their empty state or not at all; reference sample data lives only on
`/demo`.

## 0. Prompt-to-repo substitutions

| Prompt says | Repo reality | Substitution used |
|---|---|---|
| Ads config per `docs/ads/vertical-onboarding.md` | That doc does not exist (no `docs/ads/`) | The proven M6/U1 config-only recipe from `polish-u1.md` §binding: SLOT_KEYS entry (`backend/core/modules/ads/service.py`), house seed (`scripts/seed_house_ads.py` — own `Agri.in House` advertiser), slot size (`scripts/seed_sample_media.py`), slot-keys serve test extended. Engine untouched. |
| NEW shared tokens `--alert-bg/--alert-border/--alert-ink` | `--alert-bg`/`--alert-line` already exist as the generic notice style across milk.in forms + both consoles | Entered as `--severe-bg/--severe-border/--severe-ink` (design-system.md §1.2b) |
| "grid renders 36 from data" | Registry held exactly 1 row (`milk`) | Migration `0037_agri_verticals.py` seeds all 36 with grid metadata in `nav_placement.agri_home {group, order, icon, soon}` — no schema change |
| `agri_today` flag read by the frontend | No frontend flag reader / public flags endpoint exists | Flag is consumed at the API boundary: flag OFF → today endpoint absent/404 → `fetchToday()` null → sections ABSENT from DOM. Flag row exists in `public.feature_flags` (0037), OFF. |
| Section 13b live activity feed | No feed endpoint exists | `agri_live_feed` flag seeded OFF; section absent — no fabricated events |
| §11 knowledge + news via content module (E6) | `modules/content` is an empty stub (no routes) | Section absent from DOM until A-U3. **CLOSED at A-U3 W1**: module built (0045), §11 renders from approved items — see §2 below |
| §10b equipment via `/catalog` products | No agri vertical has a spec schema yet (products 404) | Section absent from DOM until Stage B |
| Branch `feat/agri-u1-home` | Session instruction | `feat/agri-d40-home-today-strip` |
| A1 reveal/stagger/count-up motion on the home | ~15 hydration islands walking a 6000px DOM were the measured anchor under the AG-A8 0.90 floor (three CI rounds) | DEFERRED on `/` by Decision 3 (perf outranks decorative motion; the milk StatBand precedent): sections render statically visible — which IS the reference's own reduced-motion fallback. `/demo` keeps the full motion spec; a cheaper mechanism (CSS scroll-driven animations) may restore it post-launch. |

## 1. Binding proofs (§ = A1 reference section)

> Chains recorded at CP2 (flag off); the full locale/breakpoint capture set
> lands at CP3. CP2 guest-home proofs: `a1/home-cp2-1280.png` +
> `a1/home-cp2-360.png` (dev backend, zero console errors; hero serving the
> seeded house campaign — live serve response:
> `GET /ads/serve?slot=agri_home_hero_xl&pincode=641001` → 200 with the
> `Agri.in House` creatives). Rows marked *absent* are the honesty rule
> working as designed.

| § | Section | Binding chain | Verdict |
|---|---|---|---|
| 1 | Utility strip + eco links | static i18n + eco links → https://milk.in / https://theorganic.in | Bound (CP2) |
| 2 | Header guest/signed state | `useAgriUser` (BFF `/api/auth/*` → id.agri.in) · coins `/api/coins/balance` · bell `/api/notify` — coins/bell/avatar inside `SignedIn`, guest gets Login pill; no secret → guest, never 500 | Bound (CP2) |
| 2b | Severe alert strip | CP3: `fetchToday()` → `GET /market/today/{pincode}` (STUB-until-A-U2, agri_today-gated) → renders ONLY when `severe_alert` non-null; flag OFF → ABSENT (0 nodes) | Bound (CP3, stub) |
| 3 | TODAY strip | CP3: TodayStrip/TodayTile from the payload (weather/mandi/schemes tiles + ask); above-fold, no reveal; flag OFF → ABSENT | Bound (CP3, stub) |
| 4 | Hero ad `agri_home_hero_xl` | AdCarousel → `serveAds()` → `GET {API}/ads/serve?slot=agri_home_hero_xl&pincode=…` → ads engine (config-only slot; house creatives seeded) | Bound (CP2) |
| 5 | Search band | form GET `action="/categories"` + `name="q"` (no `/search` route exists in web-agri; the CP3 categories screen's client filter reads `q` — the federated `/search` facade re-points this at A-U4/D52) · mic = labelled entry stub · location chip → `/api/identity/location` → `POST /identity/location` | Bound (CP2) |
| 6 | Category grid ×36 | `fetchVerticals()` → `GET {API}/catalog/verticals?limit=50` → `directory.vertical_registry` (36 rows, groups/order/icon/soon from `nav_placement.agri_home`); zero hardcoded lists | Bound (CP2) |
| 6b/7/7b/8/9 | Ticker · mandi cards · calendar · weather · schemes | CP3: all render FROM the TodayPayload (frozen in @agri/types): Marquee items, 8 MandiCards (spark=series_30d, wa.me share built server-side), SeasonCalendar, wx strip + advisory + tip, scheme cards with `verified_against`/`verified_on` stamps + DeadlinesBar (72 HRS/14447) — every source/as-of stamp is data; flag OFF → ABSENT | Bound (CP3, stub) |
| 9b | Sarkari services hub | `data/sarkari.{json,ts}` (6 official portals, https + domain + `verified_on` rendered from data; links only — no record storage, DPDP) + `scripts/check-sarkari-links.mjs` (gov.in/nic.in allowlist, host-matches-domain, liveness; run 2026-08-15: 6/6 OK) | Bound (CP3, real) |
| 10 | Directory row | `fetchDirectoryRow` → `GET {API}/directory/covers/{pincode}?limit=3` (the public nearby read; `/directory/businesses` is the private "my businesses" route) + review signals (`/reviews/summary`, `/reviews?limit=2`) → up to 3 organic VendorCards; NO sponsored card this pass (no listing-injection campaign exists for agri — organic only, honesty rule) | Bound (CP2) |
| 10a2 | How agri.in works | static i18n | Bound (CP2) |
| 10b | Equipment showcase | no products for pincode → ABSENT | Absent (honesty) |
| 11 | Knowledge + news | content module empty → ABSENT | Absent (honesty) |
| 11b/11c | Q&A / events | honest Soon cards → Soon landings (CP3 route) | Bound (CP2, Soon state) |
| 12 | Ask-AI band | entry surface + disclaimer only; assistant is A-U4 | Bound (CP2, entry only) |
| 13 | Helpline band | `apps/web-agri/data/helplines.ts` — human-verified numbers with source + verified_on rendered from data | Bound (CP2, dataset seed) |
| 13b | Live activity feed | `agri_live_feed` OFF, no endpoint → ABSENT | Absent by flag |
| 14 | Stats band | CountUp over fetched values only: verticals = `fetchVerticals().length` (36, registry) · reviews = Σ `rating_count` from `/reviews/summary`. "Businesses listed"/"pincodes covered" cells OMITTED — `covers()` returns no total and no agri coverage feed exists; no literals, no fake cells | Bound (CP2) |
| 14b | Pillars + story | static i18n; story marked illustrative, number chips omitted in prod | Bound (CP2) |
| 15/15b | Reviews + earn row | approved reviews via `/reviews` (engine serves approved only); earn row WITHOUT coin amounts — no public coins-rules endpoint exists, and invented numbers would violate the honesty rule (amounts return when the rules read lands) | Bound (CP2) |
| W2 | /categories | Registry-driven A2 screen: 36 tiles = `GET /catalog/verticals`, live/soon counts from data, client filter reads `?q=` (search band target) | Bound (CP3) |
| W2 | /c/[slug] Soon landing | Registry lookup (unknown → 404), ALWAYS noindex; notify-me → BFF `/api/leads/pincode-interest` → `POST /leads/pincode-interest` (D23 pincode-interest module — recorded per prompt) → 201; live verticals route to real surfaces | Bound (CP3) |
| 10c | Farm calculators /tools | Client-side only (zero network, offline-capable): EMI · seed rate (TNAU kg/ha) · fertilizer (FCO nutrient fractions) · spray dilution; maths in @agri/ui with 12 unit tests | Bound (CP3, real) |
| W3 | Payload contract | `market_data/schemas.py` ⇄ `@agri/types` TodayPayload, field-for-field; determinism + shape + flag-off-404 covered by `tests/test_market_today.py` | Frozen (CP3) |
| 16 | Popular searches | OMITTED — no route accepts a search query today; phrase chips pointing at category landings would mislabel. Returns with the search facade | Absent (honesty) |
| 17 | CTA tiles | "Post my need" → `/account/inquiries` (no post-need route yet) · "List my business" → `/business` console | Bound (CP2) |
| 18 | Mandi-alert opt-in | AlertCard client island, CTA → `/notifications` (real notify surface); session-only dismiss | Bound (CP2) |
| 19 | PWA install band | OMITTED — web-agri has no manifest/service worker yet; an install band would be a lie. Returns at A-U4/D53 PWA parity | Absent (honesty) |
| 20 | FAQ | 6 Q&As i18n + `FAQPage` (+WebSite/Organization) JSON-LD for https://agri.in | Bound (CP2) |
| 20b | Weekly digest | Soon state, notify-me wiring at CP3 | Soon (CP2) |
| 21–23 | Family · footer · bottom nav | static + eco; bottom nav Home · Mandi · Ask · Alerts · Profile | Bound (CP2) |


## 2. A-U3 binding proofs (§ = A1 reference section)

| § | Section | Binding | State |
|---|---|---|---|
| 11 | Knowledge + news | E6 content engine, live. Cards + news rail come from ONE `fetchKnowledgeSection()` call that dedupes them against each other (they were rendering the same three stories when built as two fetches — caught in the first capture). Every card and headline carries `source_name` + the PUBLISHER's `published_at`, read from the row. Section ABSENT when nothing is approved — the A-U1 note here said "no lorem articles, ever", and that is now enforced by data rather than by a comment | Bound (A-U3 CP1, real) |
| 11 | Knowledge hub `/knowledge` | Kind filters are server-rendered LINKS, not an island: `?kind=video` re-renders on the server, works with JS off, and is crawlable. Unfiltered-empty 404s (no heading over an empty grid); filtered-empty gets a message, because there the reader asked a question | Bound (A-U3 CP1, real) |
| 11 | Item page `/knowledge/[slug]` | Attribution above the fold; "Read it at {source}" is the primary action and feed items carry NO body — the article belongs to its publisher. Pending, rejected and unknown slugs 404 identically, so a slug guess cannot enumerate the queue | Bound (A-U3 CP1, real) |
| 11 | Video embed | `embed_url` is BUILT server-side from a code-side provider allowlist; the page never receives markup or an origin, so there is no iframe HTML to sanitise. Zero video rows at CP1 by owner decision — code path and tests green | Built, unpopulated |
| 11 | Bookmarks | The entire client footprint of the content surfaces: one optimistic toggle through the new `/api/content` BFF, bearer stays server-side (D10) | Bound (A-U3 CP1, real) |

### A-U3 prompt-to-repo substitutions

| Prompt says | Repo reality | Substitution used |
|---|---|---|
| "A-U1 and A-U2 are complete on this branch, unmerged … PR #34" | Both are IN `dev` (merged via PRs #73/#74); `feat/agri-d44-ag-a8` was 1 commit ahead of `dev` at A-U3 start, and `ads/service.py`'s `agri_home_hero_xl` entry is already in dev, NOT in this branch's diff | Work continues on the same branch, committed locally, unpushed. PR number to be confirmed by the owner at push time |
| Read `docs/ads/vertical-onboarding.md` before W4 | Still does not exist (recorded in §0 above at A-U1) | Unchanged: the M6/U1 config-only recipe. Per A-U3 §W4 the missing recipe IS the escalation — raised at CP1, resolved at CP3 |
| Checklist rows AG-A22…A30 | A-U2 already used AG-A22…A25 | Appended as AG-A26…A34 with a mapping note (owner-confirmed 2026-08-17) |
| RSS source list incl. PIB | `pib.gov.in` RSS answers **403** to a declared bot User-Agent | PIB EXCLUDED, not worked around: the only way past a 403 is to disguise the client. Three curated sources seeded instead (ICAR, The Hindu, BusinessLine), each with a `terms_note` and a robots.txt check dated 2026-08-17 |
| Video with `duration` | No keyless official API reports YouTube duration; scraping the watch page is out of bounds | `duration_seconds` nullable + curator-entered; card renders without the pill when unknown. Owner chose to ship CP1 with no video rows |
