# Agri.in hub — build plan A-U1 → A-U4 (maps blueprint D52–D69)

**Status:** ACTIVE · owner-approved 14 Aug 2026
**Predecessor:** Milk.in U1–U3 merged; U4 fix batch + checklist sign-off pending (parked, see Decision 2)
**Design references (frozen spec):** `docs/design-reference/agri/` — `agri_home_desktop_v1.html` (A1, authoritative for home), `agri_pages_public_v1.html` (A2), `agri_pages_console_v1.html` (A3), `agri_pages_mobile_v1.html` + `agri_home_mobile_v1.html` (A4, mobile truth)

---

## Decision record

**Decision 1 — sequencing flip.** Agri.in hub launches **before** TheOrganic.in, flipping the
blueprint order (D51 organic → D69 agri). Owner decision, 14 Aug 2026. This is safe because the
only organic-specific pre-work the hub depended on was the ad engine's config-only portability,
and that was proven at M6 with `theorganic_global_header` serving via config alone. Consequence:
TheOrganic.in launch re-slots after the agri launch, alongside the milk.in correction batch.

**Decision 2 — milk.in parked, not forgotten.** Milk.in minor corrections, feature encasements
and post-launch bugs are explicitly deferred until after the agri.in launch. The U4 prompt
(A1/A11/A21), the F3 logout decision, the D3/D5/D6 Razorpay rows and Issue #59 (0.90 floor
restore on `/`) remain open items in the milk track and MUST be re-raised when this plan
completes. Nothing in the agri track may silently "fix" milk surfaces.

**Decision 3 — no perf carve-out for agri.** Issue #59's 0.80 carve-out was scoped to milk `/`
only. Every agri route ships against the **0.90 throttled-3G Lighthouse merge gate** from its
first PR. Agri does not inherit the debt.

---

## Standing rules (carried from U1–U4, unchanged)

- Checkpoint sub-sprints with a human review at each; same-day merge to dev; human-only dev→main.
- "Wired" is DEMONSTRATED, not claimed — every surface gets a binding row + mutation check in
  `docs/design-reference/polish-a1.md` (sibling of polish-u1.md).
- E2E specs that assert outdated markup get their assertions MOVED — never deleted or weakened.
- Money path is line-by-line human review. Registry as data — new section types, field types,
  menu targets go in a registry, never a special case in the UI.
- Out-of-bounds categories stated in every prompt WITH reasoning.
- **New for agri (milk lesson):** the e2e acceptance checklist exists as a FILE from A-U1 day
  one (`docs/qa/agri-acceptance-checklist.md`), rows added per checkpoint — never reconstructed
  at the end.
- **New for agri (honesty rule):** a home section bound to an engine with no data renders its
  empty state or does not render — reference sample data appears only on the `/demo` route.
  Production never shows invented mandi prices, reviews, or businesses.

---

## Checkpoint map

### A-U1 · Hub home + categories + coming-soon landings (≈ D52–D53)
Prompt: `docs/design-reference/agri/A-U1_build_prompt.md` (written, ready to run).
- Home per A1 reference, every section bound to an engine that exists today
  (directory, ads-by-config, search, identity/location, leads, reviews, coins, catalog registry).
- Today strip + severe-alert strip + mandi/weather sections behind `agri_today` feature flag
  against typed stub endpoints — flag OFF in prod until A-U2 lands real workers.
- `/categories` page (all 34 registry entries, live/soon states from registry) + the shared
  coming-soon landing (self-noindexed, notify-me) for every non-live vertical.
- Starts `docs/qa/agri-acceptance-checklist.md` with the A-row skeleton.

### A-U2 · Market data engines — the Today strip becomes real (≈ D54–D56)
- `market_data` module grows: Open-Meteo hyperlocal weather (+ severe-alert banners, cached),
  Agmarknet mandi worker (90-day backfill, quality checks, source + as-of stamps — the module
  CLAUDE.md rule), commodity × market ISR pages + Dataset JSON-LD, trends + price alerts.
- Schemes dataset v0 (E5): human-verified entries with official-source + last-verified stamps.
- Flip `agri_today` ON; delete stubs; regression specs move with the markup.
- External data traps: data.gov.in 10-row cap + case-sensitive filters (already noted in
  module CLAUDE.md); Agmarknet outages must degrade to "last updated" stamps, never blanks.

### A-U3 · Content, helplines, ads activation (≈ D57–D62)
- News ingest (RSS + curation + attribution) and knowledge CMS surfaces (E6), EN/TA/HI.
- Helpline band + offline click-to-call page (D59) — helplines are E5 data, human-verified.
- **Ads activation via config only** (D62): agri slot entries per
  `docs/ads/vertical-onboarding.md`; hub rate-card entries; house creatives seeded. Engine code
  changes are OUT OF SCOPE — if the recipe doesn't suffice, stop and escalate (that voids M6's
  portability proof and is a defect, not a workaround).
- Popular-searches ISR chips; digest band remains in Soon state (backlog: retention).

### A-U4 · Coins, search, AI assistant, hardening → D69 launch (≈ D63–D68)
- Coins full activation (all earn+burn), coins center; unified notification center;
  federated search with dairy/organic cards on hub (D64).
- AI assistant (D60–61 scope): pgvector RAG, read-only mandi/weather tools, injection defense,
  tier limits, red-team run, **owner sign-off on dosage/scheme/loan content** — the assistant
  entry ships in A-U1 as a coming-soon surface; it goes live only inside this checkpoint.
- PWA parity + Lighthouse sweep (0.90, all routes), full QA, delta adversarial audit + k6,
  restore drill, launch dry-run → **D69: merge dev→main, tag v1.2.0-agri, DNS cutover.**

### Post-launch queue (in order)
1. Milk.in batch: U4 (A1/A11/A21) → re-run checklist rows + D3/D5/D6 → sign → Issue #59 floor
   restore → F3 logout decision recorded.
2. TheOrganic.in launch prep (ads already config-proven).
3. Android TWA · CMS engines · RBAC v2 (per existing roadmap).

---

## Launch gate for D69 (agri)
All A-rows of `docs/qa/agri-acceptance-checklist.md` green in a live-browser run · Lighthouse
≥ 0.90 on every agri route (no carve-outs) · a11y + SEO 100 held · adversarial audit zero
Critical/High · k6 with ads serving · restore drill executed · registry shows every non-live
vertical honestly marked Soon · AI assistant either signed-off or feature-flagged OFF.
