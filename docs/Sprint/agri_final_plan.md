# Agri.in — FINAL plan v2 (re-sequenced calendar · blueprint v7)

**Status:** FINAL v2 · 14 Aug 2026 · supersedes v1 by inclusion (nothing removed)
**Blueprint:** `docs/Schedule_Plan_v7.html` (130-day master, re-sequenced) — days 1–39 DONE.
**UI truth:** `docs/design-reference/agri/` — A1 FINAL v4 home + A2/A3/A4 bundles.
**Build prompt:** `docs/design-reference/agri/A-U1_build_prompt.md` (FINAL v2, gap items merged).

---

## Decisions in force

**D1 — sequencing (updated).** Milk.in is LIVE (D39 ✓). New order: **Agri.in hub builds now
(D40–57) → Milk.in correction batch closes (D58–62, checklist SIGNED) → TheOrganic.in
(D63–74) → Stages B–E (D75–130).** Rationale: the hub is the ad-rich centre of the ecosystem
and the M6 portability proof means both later launches inherit the ad engine as pure config;
the milk batch lands immediately after the hub launch so its lessons (perf floor, Razorpay
closure, logout semantics) are settled before the organic launch reuses those same paths.

**D2 — milk parked with a hard landing slot.** The milk items are no longer "someday": they
own days 58–62 by name — D58 U4 fixes (A1/A11/A21 with regression specs), D59 Razorpay
D3/D5/D6 closed with TEST keys (no PASS by association), D60 Issue #59 perf floor restored,
D61 F3 logout decision implemented + ADR, D62 checklist re-run and **SIGNED**.

**D3 — no perf carve-out for agri.** Every agri route holds Lighthouse ≥ 0.90 throttled-3G
from PR one. Issue #59 was milk-only debt and it dies at D60.

**D4 — registry is how verticals grow.** 36 entries at A-U1 (`farm-tools` live,
`machinery-rental` Soon); `nurseries`, `poultry`, `fisheries`, `used-equipment` enter as Soon
registry rows in their stages. A new vertical is a registry row + landing, never a build.

**D5 — external clock.** DLT cleared ✓. Razorpay KYC is the only remaining clock: TEST mode
until it clears; live-mode is a flag flipped at D62 (or first launch after clearance). Chase
now; TEST keys close D3/D5/D6 at D59 regardless.

---

## Calendar (blueprint v7 day numbers)

### A-U1 · D40–41 — Hub home + categories + landings
Prompt: `A-U1_build_prompt.md` FINAL v2. Home per A1 FINAL v4 bound to existing engines;
`agri_today` flag + typed stubs (contract frozen in `packages/types`); 36-tile registry grid;
`/categories`; coming-soon landings; **sarkari services hub** (PM-Kisan status, Patta/Chitta,
PMFBY + 72-hr, AgriStack, SHC, eNAM — verified links only, never record storage);
**calculators v1** (EMI, seed rate, fertilizer dose — offline client-side); WhatsApp share on
price cards; acceptance checklist FILE started (AG-A1…A13).

### A-U2 · D42–44 — Market data becomes real
D42 weather (Open-Meteo + severe + rainfall/monsoon departure) · D43 mandi worker (Agmarknet,
90-day backfill, arrivals, source+as-of stamps) · D44 trends + price alerts + **MSP dataset +
overlay** + **multi-market compare** + commodity SEO pages; flip `agri_today` ON, delete
stubs, specs move with markup.

### A-U3 · D45–47, D50 — Content, helplines, ads
D45 news ingest + **video content type** · D46 knowledge CMS + **pest-alert advisory type** +
livestock/poultry pack seeds · D47 hub directory + helpline band (offline page) + schemes
static v0 · D50 **ads activation via config only** (vertical-onboarding.md; engine edits =
defect, escalate).

### A-U4 · D48–49, D51–56 — AI, coins, search, hardening
D48–49 AI assistant build + hardening + red-team + **owner sign-off or flag OFF** · D51 coins
full activation · D52 unified notifications + federated search · D53 PWA parity + **mandi
offline cache** + Lighthouse sweep · D54 full QA · D55 adversarial audit + k6 with ads ·
D56 launch prep + restore drill #3 + sarkari link checker green.

### ★ D57 — Agri.in launch (tag v1.2.0-agri)
Gate: all AG checklist rows green in a live browser · ≥0.90 every route · a11y+SEO 100 ·
zero Critical/High · k6 with ads · restore drill done · every non-live vertical honestly Soon
· AI signed-off or OFF · sarkari links verified ≤7 days old · no invented data outside /demo.

### D58–62 — Milk.in corrections (★ D62: checklist SIGNED)
As Decision 2. Output: milk track formally closed; live-mode billing flag readiness noted.

### D63–74 — TheOrganic.in (★ D74: launch, tag v1.3.0-organic)
Unchanged scope from v6 blueprint days 40–51, now with the ad engine + billing paths already
battle-tested twice.

### D75–130 — Stages B → E (gates ★ D92 · D107 · D115 · ★ D130 full launch, v2.0.0)
Stage B adds **machinery-rental/CHC live** (D82) and **nurseries** (D79); Stage E adds
**used-equipment** on the classifieds core (D117); D111 may graduate the Weekly Field Report
digest out of its Soon state if metrics justify.

### Post-launch backlog (unchanged)
Photo crop doctor (after AI sign-off frame) · "my crops" stage advisory · poultry/fisheries
full surfaces · dam levels · feeder schedules · AgriCoins expiry · events monetization ·
Android TWA · CMS engines · RBAC v2.

---

## Standing rules (unchanged, binding on every checkpoint)
Checkpoint sub-sprints with human review; same-day merge to dev; human-only dev→main ·
"Wired" is DEMONSTRATED (binding rows + mutation checks in polish-a1.md) · e2e assertions are
MOVED, never weakened · money path line-by-line reviewed · registry as data · out-of-bounds
stated with reasoning · acceptance checklist lives as a file from day one · no invented data
in prod (demo route only) · new public routes require same-PR public_routes.txt entries.

## Fences (restated once)
Discovery and leads only — never selling, payments for goods, or logistics · verification and
ranking never for sale; Sponsored always labelled · verified data carries source + date ·
DPDP: consent-first reveals, export/delete, no record storage (sarkari hub links only) ·
identity consumed from AgriID, never rebuilt.
