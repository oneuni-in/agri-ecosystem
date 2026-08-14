# A-U1 — Agri.in hub home + categories + coming-soon landings (FINAL v2)

**Schedule slot: days 40–41 of blueprint v7** (`docs/Schedule_Plan_v7.html`). Plan:
`docs/Sprint/agri_final_plan.md` (FINAL v2). Gap-analysis P0 items are merged below — there
is no separate addendum.

**Work package for a Claude Code session on this repo. Read fully before writing code.**
Branch: `feat/agri-u1-home` off `dev`. Checkpoint sub-sprints below; human review at each;
same-day merge to dev when green.

---

## 1 · What this is

Bring `apps/web-agri` home from its current shell to the approved A1 design reference, add
`/categories` and the shared coming-soon landing, and start the agri acceptance checklist file.
Milk.in's U1 proved the engine set; this pass is agri's equivalent, bound to the SAME engines.

**Design truth, in priority order:**
1. `docs/design-reference/agri/agri_home_desktop_v1.html` (**A1 FINAL v4**) — home structure, all breakpoints
   (it is responsive; its <768px behavior is the mobile spec, cross-checked against
   `agri_home_mobile_v1.html`).
2. `docs/design-reference/agri/agri_pages_public_v1.html` — `#/categories` screen + Soon-tile
   behavior; its category/product/business/auth screens are for LATER passes (do not build).
3. Animations in the references are part of the spec: reveal-on-scroll, staggered tile pop-in,
   count-up stats, marquee tickers, sponsored glow — every one gated by
   `prefers-reduced-motion` with a static fallback where content stays fully visible (the
   reference files show the exact fallback behavior; replicate it, including the sparkline
   `stroke-dashoffset` and stagger `opacity` overrides).

**Theme tokens:** the references introduce the agri vertical layer (`--ag`, `--ag-deep`,
`--ag-soft`, `--ag-soft-2`) plus NEW shared tokens `--up`, `--down`, `--monsoon`,
`--alert-bg/--alert-border/--alert-ink`. Enter them in the design system
(`docs/design-system.MD` + tokens source in `packages/ui`) BEFORE first use — the U1 lesson:
token changes are cross-vertical and must be deliberate, reviewed entries, not drive-by CSS.

---

## 2 · Scope — three workstreams

### W1 · Home (`apps/web-agri/app/page.tsx`)

Rebuild per A1 reference. Sections and their bindings — **every row here becomes a binding
proof row in `docs/design-reference/polish-a1.md` (screenshot + the API call shown) and a row
in `docs/qa/agri-acceptance-checklist.md`:**

| # | Section (A1 ref) | Binding | Notes |
|---|---|---|---|
| 1 | Utility strip + eco links | static + eco-strip composite | milk.in / theorganic.in links live |
| 2 | Header, guest state | identity via BFF (`useAgriUser`) | logged-out: Login pill, no coins/bell (F1 rule: no secret → guest, never 500) |
| 2b | Severe-weather alert strip | `agri_today` flag → stub | renders ONLY when flag on AND alert active |
| 3 | TODAY strip (weather · mandi · schemes · ask) | `agri_today` flag → typed stubs | see W3; flag OFF = section absent from DOM (assert node count, not visibility — A11 lesson) |
| 4 | Hero ad slot `agri_home_hero_xl` | ads engine, **config only** per `docs/ads/vertical-onboarding.md` | approved house creatives; "Ad" tag; carousel; zero CLS. Engine code edits = defect, stop and escalate |
| 5 | Search band | `/search` facade + `/identity/location` | federated query search, mic entry stub, location chip real |
| 6 | Category grid, **36** verticals, 5 groups | `/catalog/verticals` registry | ADD registry entries `farm-tools` (live) + `machinery-rental` (Soon · CHC) in this pass — the grid renders 36 from data; zero hardcoded category lists; Soon tile → W2 landing |
| 6b/7 | Mandi ticker + mandi cards + sparklines + **WhatsApp share chip per card** | `agri_today` flag → stubs | source + as-of stamp rendered from payload, never hardcoded; share works against stub data too |
| 7b | Kharif calendar | `agri_today` flag → stub | E5-shaped payload |
| 8 | Weather strip + spray advisory + tip | `agri_today` flag → stubs | |
| 9 | Schemes spotlight + deadlines bar (incl. **PMFBY 72-hr intimation chip**, wraps on mobile) | `agri_today` flag → stub | E5 shape incl. `verified_against` + `verified_on` fields — UI renders the stamp from data |
| 10 | Directory row "businesses near you" | `/directory` by pincode | REAL data; sponsored card only if a real campaign exists, else organic-only (honesty rule) |
| 10a2 | How agri.in works | static | steps composite |
| 10b | Equipment showcase | `/catalog` products | render ONLY if products exist for the pincode; else section absent |
| 11 | Knowledge + news | content module (E6) | empty module → section absent; no lorem articles in prod |
| 11b/11c | Q&A preview / events | static coming-soon variants | Stage D surfaces: render as Soon cards linking to landing, not fake threads |
| 12 | Ask-AI band | entry → coming-soon landing | assistant itself is A-U4; disclaimer copy ships now |
| 9b | **Sarkari services hub** — PM-Kisan status · Patta/Chitta · PMFBY · AgriStack · SHC · eNAM | E5 dataset of official links (`verified_against`/`verified_on` fields) | REAL in this pass — links open OFFICIAL portals only; we never fetch or store records (DPDP). Add a link-checker script for the acceptance row |
| 10c | **Farm calculators** — EMI · seed rate · fertilizer dose (from SHC values) · spray dilution if time allows | static client-side, offline-capable, under `/tools` | REAL in this pass; registry entry `farm-tools` points here |
| 13 | Helpline band | E5 helplines dataset | REAL — seed the small human-verified helpline set in this pass (numbers verified against official sources, source+date in data) |
| 13b | Live activity feed | notify/event bus derived, anonymised | if the feed endpoint doesn't exist, ship section behind `agri_live_feed` flag OFF — do NOT fabricate events |
| 14 | Stats band count-up | real counts (directory/coverage) | numbers from APIs, not literals |
| 14b | Trust pillars + success story | static copy | story quote marked as illustrative until a real consented story replaces it — or omit numbers chips in prod |
| 15/15b | Reviews strip + earn-coins row | reviews (approved only) + coins rules | |
| 16 | Popular searches | ISR links to real routes | only link routes that resolve (search or category landings) |
| 17–20 | CTAs, mandi-alert opt-in, PWA band, FAQ | leads / notify / PWA / JSON-LD | FAQ gets FAQPage JSON-LD; digest band ships in its **Soon** state (notify-me only, no reader-count claims) |
| 21–23 | Family strip, footer, bottom nav | static + eco | bottom nav: Home · Mandi · Ask · Alerts · Profile |

**Localisation:** EN/TA/HI via next-intl for every string above, glossary at
`docs/i18n-glossary.md`. Tamil strings from the reference are starting points, not final —
flag any that read wrong for review.

### W2 · `/categories` + coming-soon landing
- `/categories`: A2 reference screen — searchable (client-side filter), 5 groups, counts,
  live/soon from registry, breadcrumb, zero hamburgers.
- ONE shared coming-soon landing route (e.g. `/c/[vertical]/soon` or the vertical's own route
  rendering the Soon state — follow existing routing conventions in web-agri): honest copy,
  self-noindexed (`NoIndex` primitive), notify-me wired to a real subscription (pincode-interest
  or notify module — whichever the engines already support; record which in the proof row).
- Live essentials tiles route to their real existing surfaces (search, directory, notifications)
  or their flagged sections' landings — no dead links anywhere (assert in e2e).

### W3 · `agri_today` flag + typed stubs
- One feature flag `agri_today` (existing flags mechanism from D3 foundation).
- Typed stub endpoint(s) in `market_data` (e.g. `GET /market/today/{pincode}` returning
  weather + mandi + schemes + calendar in the A-U2 production shape) — clearly marked stubs,
  deterministic fixture data, `public=True` ONLY with the same-PR `public_routes.txt` entry and
  a comment marking it stub-until-A-U2. If adding a public route for a stub feels wrong,
  alternative: serve fixtures from the Next side behind the flag and add the backend route in
  A-U2 — pick one, write the reasoning in the PR description.
- The A-U2 session must be able to replace fixtures with real workers WITHOUT touching the UI:
  the payload contract is the deliverable here. Freeze it in `packages/types`.

---

## 3 · Demo-equals-product
Every new visual shape (Today card, mandi card + sparkline, calendar, deadline bar, pillar,
story, earn row, tip card, eyebrow, wave divider) enters `packages/ui/src/composites/` —
extend `home-patterns.tsx` / `today-strip.tsx` / `category-group.tsx` where shapes already
exist rather than forking. The `/demo` route gains an A-U1 section rendering each new
composite with the reference's sample data — that is where reference sample data lives, and
nowhere else.

## 4 · Regression specs (write them, don't just check manually)
Every section: a spec asserting DOM SHAPE (counts for flag-off absence — never visibility),
guest vs logged-in header, registry-driven tile count = registry entry count, Soon tiles are
noindexed landings, FAQ JSON-LD present, reduced-motion static fallbacks (sparklines visible,
tiles opacity 1), EN/TA/HI locale contexts (one browser context per locale — NEXT_LOCALE trap),
ads frequency-cap reset before any repeated-load script (`ads_freq_cap_per_day = 3`), no
`waitUntil: "networkidle"` anywhere (coins pill/bell/carousel poll), `.tap-target` never
combined with `position:absolute`, no `bg-<color>` beside gradient classes through `cn()`
(use arbitrary property for solid underlays), production build without `AUTH_SESSION_SECRET`
renders guest home (§2b milk lesson — add the spec for agri explicitly).

## 5 · Acceptance checklist file (start it NOW)
Create `docs/qa/agri-acceptance-checklist.md` with rows: AG-A1 guest home clean console ·
AG-A2 registry grid = registry · AG-A3 Soon landing noindex + notify-me round-trip · AG-A4 ads
slot serves + caps + labelled · AG-A5 search band → results · AG-A6 directory row real data ·
AG-A7 locale sweep · AG-A8 Lighthouse ≥ 0.90 `/` `/categories` · AG-A9 reduced-motion sweep ·
AG-A10 no-secret guest render · AG-A11 sarkari links resolve to official domains + stamps render
from data · AG-A12 calculators compute correctly offline · AG-A13 grid renders exactly the
registry (36). Mark each row's verification method. Rows are appended by
later checkpoints, never rewritten.

## 6 · Checkpoints (human review at each)
1. **CP1:** tokens + composites + `/demo` section (all new shapes reviewable in isolation).
2. **CP2:** home assembled, flag off — real-engine sections bound, proofs drafted.
3. **CP3:** flag-on stubs + `/categories` + Soon landing + specs + checklist + screenshots at
   360/390/768/1280 in EN/TA/HI → PR to dev.

## 7 · Out of bounds — with reasoning
- **Milk.in, TheOrganic.in, web-id, web-admin surfaces:** parked by Decision 2; a "small fix"
  there doubles review surface and breaks the parked-track bookkeeping. If agri work exposes a
  cross-vertical bug, file an issue, don't fix it here.
- **Ads engine code:** M6 proved config-only onboarding; touching engine code here voids that
  proof. Config + creatives only.
- **Today-strip real workers (Open-Meteo/Agmarknet):** A-U2's whole job; the flag exists so
  this pass can't be tempted into half a worker.
- **AI assistant beyond the entry surface:** safety sign-off path (D61) is owner-gated;
  shipping any live assistant behavior early bypasses a deliberate human gate.
- **Shared token edits beyond the listed new tokens:** U1's `--call`/`--rating` lesson —
  cross-vertical blast radius needs design-system entries, not incidental edits.
- **Perf carve-outs:** Decision 3 — agri holds 0.90 from PR one; a carve-out request here is a
  red flag, not an option.
- **Vendor subscriptions / paid ranking of any kind:** structurally barred (M3); advertising
  sells placement, never ranking — reference copy states it, code must honor it.
- **New public routes** without same-PR `public_routes.txt` entries: CI will fail you anyway;
  don't negotiate with the gate.

## 8 · Done means
CP3 merged to dev · binding proofs in polish-a1.md · registry shows 36 (tools live, rental
Soon) · sarkari hub live with link checker · calculators v1 usable offline · checklist file exists with A-U1 rows
verified · Lighthouse ≥ 0.90 both routes · zero console errors as guest (milk's A1 failure —
don't repeat it on agri) · screenshots archived · A-U2 payload contract frozen in types.
