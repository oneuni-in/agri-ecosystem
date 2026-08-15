# Agri.in acceptance checklist (AG rows)

Started at A-U1 CP1 per the build prompt §5. **Rows are appended by later
checkpoints/passes, never rewritten.** A row goes ✅ only with evidence — a
binding proof row in `docs/design-reference/polish-a1.md`, a spec file, or a
recorded run — never by assertion. Launch gate (D57): every row green in a
live browser.

| Row | Acceptance | Verification method | Status |
|---|---|---|---|
| AG-A1 | Guest home renders with a clean console (zero errors/warnings) — milk's A1 failure not repeated | Live browser as guest at 360/1280, DevTools console capture archived; e2e spec asserts no `console.error` on load | 🟡 implemented (guest 200, zero console errors on live captures at CP2+CP3); flips ✅ when the agri-home e2e spec runs green in CI |
| AG-A2 | Category grid renders exactly the registry — tile count = registry entry count, zero hardcoded category lists | e2e spec: fetch `/catalog/verticals`, assert DOM tile count equals registry count; code review: no literal category arrays in app code | 🟡 implemented (home + /categories render 36 from the registry; spec in CP3 e2e batch) |
| AG-A3 | Soon landing is self-noindexed and notify-me round-trips to a real subscription | e2e: assert `noindex` meta on landing; submit notify-me, assert 2xx + row via API; proof row records which module (pincode-interest vs notify) | 🟡 implemented — /c/[slug] always noindex; notify-me → D23 pincode-interest (BFF 201 verified); spec in CP3 e2e batch |
| AG-A4 | `agri_home_hero_xl` ad slot serves approved house creatives, respects frequency caps, always labelled "Ad", zero CLS | e2e with cap reset before repeated-load (`ads_freq_cap_per_day = 3`); Lighthouse CLS on `/`; visual check of the Ad tag; config-only diff (no engine code edits) | ⬜ pending (CP2) |
| AG-A5 | Search band submits to `/search` and returns results; location chip reflects `/identity/location` | e2e: type query → results page renders hits; binding proof row with the real API call | ⬜ pending (CP2) |
| AG-A6 | Directory row shows REAL businesses for the pincode; sponsored card only when a real campaign exists, else organic-only | Binding proof row (screenshot + `/directory` call); e2e against seeded dev data asserts organic-only when no campaign | ⬜ pending (CP2) |
| AG-A7 | Locale sweep: EN/TA/HI render every home/categories string via next-intl; no hardcoded copy; Tamil strings flagged where they read wrong | e2e: one browser context per locale (NEXT_LOCALE trap); screenshot set 360/390/768/1280 × EN/TA/HI archived | 🟡 spec green locally (per-locale contexts in agri specs) + 24-shot matrix archived in a1/; flips ✅ on CI green + native TA/HI review |
| AG-A8 | Lighthouse ≥ 0.90 (throttled-3G) on `/` and `/categories` — no carve-out, from PR one | LHCI run per route in CI + local run recorded; Decision 3 forbids exceptions | ⬜ pending (CP3) |
| AG-A9 | Reduced-motion sweep: every animation static with content fully visible (sparklines drawn, tiles opacity 1, marquee static, count-up shows finals) | e2e with `prefers-reduced-motion: reduce` context: assert sparkline visible, tile opacity 1, stat values final; spec per §4 of the build prompt | 🟡 reduced-motion spec green locally (dashoffset 0, tiles opacity 1, marquee static); NOTE: reveal/count-up motion deferred on the home under the AG-A8 floor (polish-a1 §0) — static state = the rm fallback, so this row's guarantees hold trivially there; flips ✅ on CI green |
| AG-A10 | Production build without `AUTH_SESSION_SECRET` renders the guest home — no secret → guest, never 500 | Spec: build + boot without the secret, assert 200 + guest header (milk §2b lesson, agri-explicit) | ⬜ pending (CP2/CP3 spec) |
| AG-A11 | Sarkari hub links resolve to OFFICIAL domains only; `verified_against`/`verified_on` stamps render from data; link-checker green ≤ 7 days before launch | `scripts` link-checker run recorded; spec asserts stamp text comes from the dataset, not literals; domain allowlist review | 🟡 implemented — data/sarkari.json (https, official domains, verified_on 2026-08-15 rendered from data) + scripts/check-sarkari-links.mjs run 6/6 OK; re-run ≤7 days before launch (D57 gate) |
| AG-A12 | Farm calculators (EMI · seed rate · fertilizer dose from SHC · spray dilution) compute correctly and work offline | Unit tests per formula with hand-checked fixtures; e2e offline-mode run of `/tools`; formulas' sources cited in code | 🟡 implemented — /tools client-side, zero network; 12 unit tests green (@agri/ui agri-calculators); TNAU/FCO citations in code; offline e2e run pending |
| AG-A13 | Grid renders exactly 36 registry verticals — `farm-tools` live, `machinery-rental` Soon (· CHC) | e2e: tile count === 36 asserted against the registry response; registry diff shows the two new entries added this pass | 🟡 implemented — 0037 seeds exactly 36 (farm-tools live, machinery-rental Soon·CHC); spec asserts count vs registry in CP3 e2e batch |

## Verification legend
- **e2e** — Playwright spec committed under `e2e/`, asserting DOM SHAPE
  (counts for flag-off absence, never visibility), no
  `waitUntil: "networkidle"` anywhere.
- **Binding proof row** — screenshot + the real API call, recorded in
  `docs/design-reference/polish-a1.md` as each section is bound.
- **Recorded run** — command + output archived in the PR that flips the row.
