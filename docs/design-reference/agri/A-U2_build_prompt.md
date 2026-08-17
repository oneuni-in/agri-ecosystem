# A-U2 — Market data engines: weather + mandi become REAL (FINAL v1)

**Schedule slot: days 42–44 of blueprint v7.** Plan: `docs/Sprint/agri_final_plan.md`.
**Git context (owner decision):** A-U1 is complete on this branch but NOT yet merged to dev
(GitHub Actions limit; self-hosted runners being provisioned). A-U2 CONTINUES ON THE SAME
BRANCH and the same PR (#34 — "feat(agri-u1)…"). Prefix every commit `a-u2:` so the PR
history stays scannable. **Do NOT push until the owner explicitly says so** — commit locally
only. When runners are ready, one push updates PR #34 and triggers the full CI run that
gates the merge.

**Read before writing code:**
1. This prompt, fully.
2. The frozen Today-strip payload contract from A-U1 — locate it (packages/types or wherever
   A-U1 froze it; the A-U1 PR body records where). It is BINDING: A-U2 implements it.
3. `backend/core/modules/market_data/CLAUDE.md` — module boundary rules + the data.gov.in
   traps already recorded there (10-row cap, case-sensitive filters).
4. `docs/Sprint/agri_final_plan.md` A-U2 section.

---

## 0 · The one rule that defines this pass

A-U1 shipped the UI against deterministic fixtures behind `agri_today`. A-U2 replaces the
fixtures with real workers **without touching the UI**. The measure of success: the diff in
`apps/web-agri/app/` is near zero (deleting fixture plumbing and flipping the flag default —
nothing else). If the frozen contract turns out to be wrong or missing a field, STOP and
propose a versioned contract change for owner review — never silently drift the shape and
"fix" the UI to match.

---

## 1 · Workstreams

### W1 · Weather (D42) — `market_data` module
- Open-Meteo client (httpx, timeout + retry budget): current + 7-day per pincode, resolved
  through the existing geo centroids. Cache aggressively (per-pincode TTL ~30–60 min; Redis
  or table cache — follow existing module conventions). Open-Meteo needs no key; still treat
  the base URL as config.
- Severe-alert banners: derive from Open-Meteo weather-warning data; label the source
  honestly in the payload (`source: "open-meteo"` — do NOT label anything "IMD" unless it
  actually comes from IMD). The alert strip renders only when an alert exists.
- Rainfall actuals (last-7-days mm) + monsoon-departure-from-normal where the API provides
  it; omit the field where it doesn't — the UI already renders only what's present.
- Spray-window advisory: computed server-side from the forecast (rain-probability rule),
  marked as computed guidance, not human advice.
- Endpoints on SecureRouter, `public=True` WITH same-PR `public_routes.txt` entries and
  comments. Every payload carries `source` + `as_of`. Cursor pagination on any list.
- Weather alert subscriptions via the notify module's existing patterns (event bus, not
  direct imports — module boundary rule).

### W2 · Mandi (D43) — Agmarknet worker
- Ingestion worker for Agmarknet via data.gov.in: commodity × market × state daily prices
  (min/max/modal) + arrivals where provided. Respect the recorded traps: paginate past the
  10-row cap, exact-case filters. Be a polite client: backoff, bounded concurrency, API key
  via SOPS-managed env — NEVER committed.
- 90-day backfill job (idempotent, resumable) + scheduled daily pull (~6:00 AM IST).
- Quality checks on ingest: unit normalization, obvious-outlier quarantine (price 10× the
  30-day median goes to a review state, not the site), duplicate-row dedupe. Quarantined
  rows are visible in ops, never rendered.
- Tables in the market_data schema via the migration template (UUIDv7, UTC, soft-delete
  conventions); cursor pagination; no other module's tables touched.
- `web-agri` pages: commodity × market ISR pages with Dataset JSON-LD, noindex-until-
  populated, auto-sitemap entries — reuse the existing ISR/SEO primitives.

### W3 · Trends, alerts, MSP, compare + THE FLIP (D44)
- 30-day series endpoint feeding the existing sparklines; trends on commodity pages.
- Price alerts: subscribe (commodity × market) → morning notification after the daily pull;
  reveal/anti-abuse caps consistent with notify conventions. The home mandi-alert opt-in
  card now round-trips for real.
- MSP dataset (E5): current-season MSP table, human-verified entries with
  `verified_against` (CACP/PIB source URL) + `verified_on` dates. MSP overlay appears on
  price cards/pages where commodity maps to an MSP crop.
- Multi-market compare view on the commodity page (nearby markets, same day) — data already
  ingested; UI is one additive table on the commodity page (allowed UI addition, it's a new
  page surface, not a contract change).
- Registry: add Soon entries `nurseries`, `poultry`, `fisheries` (migration, config only —
  grid + categories page pick them up automatically; counts update from data).
- Spray-dilution calculator if A-U1 deferred it.
- **The flip:** `agri_today` default ON · delete every fixture/stub and the stub route (with
  its `public_routes.txt` line) · e2e specs that asserted stub behavior get their assertions
  MOVED to real-data assertions (assert shape + stamp presence, not exact prices) — never
  deleted or weakened.

## 2 · Honest degradation (non-negotiable)
Agmarknet down → serve last-known data with the stale `as_of` stamp visible; Open-Meteo
down → weather section renders its empty state; a pincode with no mandi coverage → empty
state with "no market data for this area yet". NEVER a blank crash, NEVER invented numbers,
NEVER a hardcoded fallback price. Write a spec for each of these three.

## 3 · Acceptance checklist additions (append rows, never rewrite)
AG-A14 weather renders real per-pincode data with source + as-of · AG-A15 mandi cards match
raw ingested rows (spot-check 3 commodities against the API) · AG-A16 price-alert
subscription round-trips and fires after a pull · AG-A17 MSP overlay values match the
verified dataset · AG-A18 compare view rows match the underlying table · AG-A19 outage
degradation shows stale stamp (kill the worker, reload) · AG-A20 zero stub/fixture code
remains (grep for the fixture markers) · AG-A21 Lighthouse still ≥ 0.90 on `/` with the flag
ON (real data must not regress perf — watch payload sizes and cache headers).

## 4 · Checkpoints (in-session review stops — NO pushes)
- **CP1:** weather module + endpoints + cache + tests; home weather/Today sections live
  against it locally (flag on in dev).
- **CP2:** mandi ingest + backfill run against the real API + quality checks + commodity
  pages; show me 3 real commodities on the home cards.
- **CP3:** trends + alerts + MSP + compare + registry entries + the flip + stub deletion +
  specs + checklist rows + screenshots (4 widths, EN/TA/HI on home + one commodity page).
  Then STOP. Owner triggers the single push when runners are ready.

## 5 · Out of bounds — with reasoning
- **UI redesign / contract drift:** the whole point of the flag was UI stability; contract
  changes need owner review (§0).
- **News, knowledge, helplines→E5 migration:** A-U3's scope — don't pull it forward.
- **AI assistant, ads engine code, coins, notifications center:** A-U4 / config-only rules
  unchanged from A-U1.
- **Milk.in / TheOrganic.in / web-id / web-admin:** parked; file issues.
- **Schemes eligibility wizard:** Stage C; A-U2 ships MSP + existing scheme cards only.
- **New heavy dependencies:** an httpx client and stdlib do this job; anything more needs
  justification in the PR body.
- **Scraping HTML:** public APIs only. If a dataset isn't available via API, it waits —
  we don't scrape portals.
- **Secrets in the repo:** API keys via SOPS/env only; gitleaks will catch you anyway.

## 6 · Done means
All three checkpoints reviewed · contract implemented unchanged (or a reviewed v2 recorded)
· fixtures fully deleted · flag ON by default · backfill + daily job proven against the real
API · honest-degradation specs green · checklist rows AG-A14…A21 filled with verification
method · binding proof rows appended to polish-a1.md (weather + mandi sections now show the
REAL API calls) · commits prefixed `a-u2:` sitting locally, ready for the owner's single
push to PR #34.
