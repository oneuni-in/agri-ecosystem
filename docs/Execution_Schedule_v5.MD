# AGRI.IN ECOSYSTEM — FINAL EXECUTION SCHEDULE v5 (MASTER — DEFINITIVE)
## 🥛 Milk.in D32 · 🌿 OrganicStore.in D44 · 🌾 Agri.in D62 · Full Ecosystem D118
### Single source of truth. Supersedes v3/v4. Reflects actual environment and current status.

**Status at issue:** Domains ✅ ready on Cloudflare · DLT ⏸ ON HOLD (hard deadline: file by ~D10–12) · Razorpay ⏸ ON HOLD (file by ~D18) · Sprint 0 spec pack ✅ delivered · Coding begins now via Claude extension in VS Code on Windows.

---

# PART 0 — THE ENGINEERING CONSTITUTION (top of root CLAUDE.md, obeyed by every session)

## 0.1 The four lines
> Endpoints are private, rate-limited, and validated unless explicitly marked public. All lists are cursor-paginated; all IDs are UUIDv7; all user content defaults to pending. All public pages are SSR/ISR with JSON-LD, immutable slugs, and pass Lighthouse 90 in CI. When in doubt: boring choice, reversible choice, measured choice.

## 0.2 Git workflow (LOCKED)
- Branches: `main` (production, protected) ← `dev` (integration/staging, protected, default branch) ← `feat/dXX{a|b}-name` (one per work package).
- **NEVER commit directly to main or dev.** Every work package: branch from dev → build → push → **PR targeting dev** → CI gates green → your review → merge same day.
- **dev → main promotion is human-only**, done at gates/launches. Tags land on promotion, not daily: `v0.1.0`@D5 · `v0.2.0`@D14 · `v0.3.0`@D22 · `v1.0.0-milk`@D32 · `v1.1.0-organic`@D44 · `v1.2.0-agri`@D62 · `v2.0.0`@D118.
- Staging deploys from **dev**; production deploys from **main** only. By launch week, "deploy to prod" = merge dev→main.
- Solo hygiene rule: no feature branch survives overnight unmerged without a written reason.

## 0.3 Vertical Slice Protocol (build order for EVERY feature)
SPEC (incl. threat-model minute: "who abuses this and how?") → 1 DB migration (reversible, reviewed) → 2 service + invariants → 3 API (SecureRouter) → 4 OpenAPI→TS types → 5 frontend on real endpoints (never mocks) → 6 tests. Data flows uphill; we build downhill. Track A runs 1–4 while Track B runs 5 against the spec'd contract.

## 0.4 Security by default
SecureRouter: every endpoint auth-guarded + rate-limited + validated by default; `public=True` is the only bypass and is CI-audited against a committed public_routes.txt. `owned_by()` helper kills IDOR structurally. Migration template ships soft-delete, audit cols, `moderation_status DEFAULT 'pending'`. App DB user cannot DROP/TRUNCATE. Uploads: presigned → re-encode → EXIF-strip → media domain. Secrets never in code or session context. Sensitive code (auth, coins, billing, leads, contact-reveal): line-by-line human review + adversarial second-pass audit — no deadline override, ever.

## 0.5 Scale: one-way doors locked now
UUIDv7 PKs · append-only coins ledger · schema-per-module · UTC timestamptz · JSONB i18n from row one · cursor pagination only (offset banned by lint) · Redis Streams events · immutable slugs + redirect table. Deferred until metrics demand: K8s, replicas, sharding, Elasticsearch. Real scaling story: 95% anonymous reads → ISR on Cloudflare edge → origin rarely touched. Instrument from D5; scale reactively with data.

## 0.6 SEO as architecture
Every public page SSR/ISR, HTML complete on first byte. URLs are schema (`/tractors/tamil-nadu/madurai`), slugs immutable, renames = 301 via redirect table. JSON-LD lives in typed components (LocalBusiness/Product/FAQPage/BreadcrumbList/Dataset). Sitemaps auto-generate from the vertical registry. Thin pages self-noindex. Lighthouse ≥90 on throttled 3G is a CI merge gate — the SEO requirement and the mid-range-Android-farmer UX requirement are the same requirement.

## 0.7 Meta-rule
Boring technology, exciting product. Innovation tokens go only to the moats: verified data, vernacular UX, trust.

---

# PART 1 — DAILY OPERATING SYSTEM

| Time | Block | Contents |
|---|---|---|
| 08:30–09:15 | REVIEW-1 | Overnight/background output → merge or reject. Monitors + slow-query log. `git checkout dev && git pull`. |
| 09:15–10:15 | SPEC | Today's 2–3 specs incl. threat-model + URL/schema decisions. Specs stay 1 day ahead. |
| 10:15–13:30 | BUILD-1 | Track A + Track B (two VS Code windows, one Claude panel each, separate feat/ branches). |
| 13:30–14:15 | Break | Non-negotiable. Decision fatigue is a security vulnerability. |
| 14:15–17:15 | BUILD-2 | Integration; line-by-line review of migrations + sensitive diffs as they land. |
| 17:15–18:30 | REVIEW-2 | Tests green → adversarial pass (sensitive) → CI gates → **PRs merged to dev** → staging. |
| 18:30–19:00 | QUEUE | Background session: translations, seed extraction, SEO copy, test gen. Tomorrow's spec stubs. |

Weekly: Day 6 = half build + drift-check (Claude audits repo vs Constitution/ADRs) + dependency audit + backup verify + slippage buffer. Day 7 OFF.

**AI-efficiency rules:** 2 foreground sessions max (your review bandwidth is the bottleneck) · fresh session per spec, small per-module context · spec-first always · template-and-repeat verticals (~70% cost cut) · edit don't regenerate · plan-mode first on big specs (D03/D04-class) · overnight batch = free hours · other AI tools only where they clearly beat Claude (image gen; transcription later).

**Environment (locked to reality):** Windows + VS Code + Claude extension. Python via `py` (3.13 — Dockerfile pins 3.13; local Python is editor-tooling only). Node 20+, pnpm 9, Docker Desktop on WSL2 backend. `git config --global core.autocrlf input`. Backend truth lives in containers, not the host.

---

# PART 2 — EXTERNAL-CLOCK ITEMS (adjusted for holds)

| Item | Status | Hard deadline | Consequence if missed |
|---|---|---|---|
| Domains + Cloudflare | ✅ Done | — | — |
| **DLT SMS registration** | ⏸ HOLD | **File by D10–12** (1–2 wk approval) | Real OTP unavailable → D32 launch slips. Mock driver keeps dev unblocked meanwhile. |
| **Razorpay KYC** | ⏸ HOLD | **File by D18** (~1 wk) | Vendor paid tiers unavailable at D32 → fallback: launch free-tier-only, billing behind feature flag. |
| Legal (object clause, coins opinion, T&C briefs) | Pending | Send by D15, answers by D30 | Launch legal pages incomplete. |
| API keys (data.gov.in, ZeptoMail, Maps) | Pending | By D20 | Blocks D36/D48 modules. |
| Pricing v1 draft | Pending | By D20 | Blocks D20 billing encoding (placeholder tiers OK). |
| Seed-data source lists (Coimbatore dairy, organic, inputs) | Pending | Rolling from D19 | Thin launch content. |

*Schedule will flag DLT again at D7 (OTP day) and D10. Do not let it pass D12.*

---

# PART 3 — DAY-WISE SCHEDULE (118 days)
[A]/[B]=parallel tracks · [BG]=background · [YOU]=solo. Every feature day = Slice Protocol. Every day ends with PRs merged to **dev**.

## ■ BLOCK 1 — FOUNDATION + DEFAULTS MACHINERY (D1–5) → promote dev→main, tag v0.1.0
- **D1** [A] SPEC D01-A: Turborepo, 5 Next.js apps, shared packages (3h) · [B] SPEC D01-B: FastAPI skeleton + **SecureRouter** (401-by-default proven by test), compose stack, two DB roles (3.5h) · [YOU] env verify, CLAUDE.md with Constitution + git rules, branch protections, dev default (2h)
- **D2** SPEC D02: tokens + 18 inclusive components (CategoryTile icon+EN+vernacular, CallButton, PincodeInput, BottomNav…) (3.5h) · SEO primitives as typed components: JsonLd variants, MetaBuilder, canonical, NoIndex + shouldNoIndex (2.5h) · a11y pass + next-intl EN/TA/HI (1.5h)
- **D3** SPEC D03 (plan-mode first): Alembic multi-schema + migration template (UUIDv7/UTC/soft-delete/moderation-pending) (3h) · cursor paginate() + offset-ban rule, owned_by(), immutable-slug mixin + redirects table + 301 middleware, JSONB TranslatedString, Redis Streams bus, feature flags (3h) · geo v1 loaded + TN verified (2h)
- **D4** SPEC D04 (plan-mode first): PR pipeline — lint/type/tests/build, migration up+down, import-linter, offset-ban, gitleaks, dep audit (2.5h) · **public-route audit gate** + **Lighthouse ≥90 throttled-3G merge gate**; staging deploy (from dev) + SOPS (3h) · Caddy security headers (1.5h)
- **D5** SPEC D05: Sentry, JSON logs + **PII-scrub with test**, request IDs, pg_stat_statements, p95 (2.5h) · encrypted backups→R2 + **RESTORE DRILL #1 actually executed & timed** + Kuma (2.5h) · ADRs + per-module CLAUDE.md; **GATE 1: clone→running <15 min; insecure endpoint fails CI** (2.5h)

## ■ BLOCK 2 — AGRIID + AGRICOINS (D6–14) — deepest-review sprint → tag v0.2.0
- **D6** identity.* schema via template (users, profiles, handles+history, otp_requests, sessions_refresh, roles, permissions, addresses, preferences) (3.5h) · @handle rules + blocklist + AG-XXXXXXX atomic fallback (2.5h) · [YOU] line-by-line schema review; privacy defaults (1.5h)
- **D7** OTP service: issue/verify, TTL, caps, backoff, per-number/IP/device limits; **mock driver primary (DLT on hold)** + vendor driver behind flag (3.5h) · DLT template stubs + delivery webhook + cost log (2h) · [YOU] paper red-team: enumeration/flooding/SIM-swap → fixes. **⚠ DLT reminder #1** (1.5h)
- **D8** OAuth2 authorization server (authlib): /authorize + /token, PKCE enforced, first-party client registry (4h) · RS256 keys + JWKS + rotation runbook (2h) · [YOU] full-flow line review (2h)
- **D9** rotating device-bound refresh, revocation, logout-everywhere (3.5h) · web-id: OTP screens, handle picker, device manager (3h) · [YOU] replay/rotation-race review (1.5h)
- **D10** auth-client SDK: BFF cookies, silent SSO, useAgriUser() (3h) · wired into all 4 apps (3h) · [YOU] one account all domains; one logout kills all. **⚠ DLT reminder #2 — file now** (1h)
- **D11** progressive profile API+UI + completion score (3h) · RBAC deps + 5 roles + admin user mgmt (3h) · [BG] Playwright auth E2E
- **D12** hash-chained audit log (2.5h) · notify module: in-app/SMS/email templates + consumers (3.5h) · [YOU] tamper-evidence verify (1h)
- **D13** AgriCoins: append-only ledger + idempotency index + award/redeem + balances + nightly integrity (4h) · rules engine + consumers + referrals + clustering flags (3h) · [YOU] line-by-line ledger review + concurrency property tests (2h)
- **D14 ★** adversarial audit auth+coins, fixes (3h) · coins widget/history + admin rules/abuse queue (3h) · **GATE 2: SSO across 3 domains · OTP-abuse suite · 10k concurrent awards zero drift** → promote, v0.2.0 (1.5h)

## ■ BLOCK 3 — SHARED CORE FOR MILK.IN (D15–22) → tag v0.3.0
- **D15** directory slice: businesses/branches/categories/claims/verifications (3.5h) · vendor↔pincode coverage + "who serves 641001" (2.5h)
- **D16** claim flow + verification-lite queue (3h) · admin business mgmt UI (3h)
- **D17** vertical_registry + versioned JSONB spec_schemas + validate-on-write (3.5h) · milk product schema + media pipeline (presign→re-encode→EXIF-strip→media domain) (3h)
- **D18** reviews (polymorphic, pending-default, ratings, coin hook) (3h) · leads: types, pincode×category routing, inbox, response tracking — threat: scraping → reveal caps (3.5h)
- **D19** Meilisearch indexers + unified API (3h) · location context (profile→GPS→pincode→IP) + switcher (2.5h) · [BG] Coimbatore vendor seed
- **D20** Razorpay subscriptions + signed idempotent webhooks + invoices + reconciliation — **behind feature flag while KYC on hold** (4h) · Business Console shell (3h) · [YOU] money-path line review. **⚠ Razorpay: file KYC now (D18 deadline passed check)** (1.5h)
- **D21** ads v1: campaigns/creatives/slots/geo targeting/approval/partitioned tracking (3.5h) · Ops Console: unified moderation queue + flags (3h)
- **D22 ★** adversarial: leads IDOR, uploads, billing (2.5h) · k6 browse load (2h) · **GATE 3: register→claim→subscribe(flagged)→receive-lead E2E** → promote, v0.3.0 (2h)

## ■ BLOCK 4 — MILK.IN BUILD & LAUNCH (D23–32)
- **D23** pincode-first home (ISR) + GPS fallback + brand/vendor blending (3.5h) · milk-type filters + price-range banner (3h)
- **D24** vendor profiles w/ LocalBusiness JSON-LD + tracked Call/WhatsApp/form (3.5h) · MapLibre map+list sync (3h)
- **D25** "post my need" icon-first speakable flow (3.5h) · coverage matching → vendor inbox → respond → notify (3h)
- **D26** vendor dashboard: listing/coverage/products/leads + response stats (3.5h) · premium tier (priority sort) + analytics-lite (2.5h)
- **D27** dairy directory (vets/feed/farms/co-ops via registry) (2h) · brand pages + shops-near-you (3h) · [BG] 150+ vendors seeded; TA/HI strings
- **D28** PWA: manifest/SW/offline shell/push (3h) · pincode landing ISR + noindex-until-populated + sitemaps (3h)
- **D29** E2E: discover→call, need→respond, subscribe (3h) · device matrix + low-data + vernacular (3h)
- **D30** adversarial full-surface + OWASP (3h) · CF production WAF/bot/rate + k6 500/50 (2.5h) · [YOU] fix triage. **DLT approval must be in hand — verify real SMS today** (2h)
- **D31** deploy dry-run + DNS/rollback rehearsal (2.5h) · legal pages live; DPDP consent/export/delete verified (2.5h) · [YOU] restore drill #2 + on-call + content seed (2h)
- **D32 — 🥛 MILK.IN LAUNCH ★** merge dev→main, tag v1.0.0-milk, DNS cutover, smoke, monitor, hotfix lane. [BG] Organic specs.

## ■ BLOCK 5 — ORGANICSTORE.IN (D33–44) — 20% daily ops budget begins
- **D33** organic taxonomy + spec schemas + category ISR landings (3h) · producer/FPO type + brand directory UI (3h)
- **D34** cert system: upload→verify→badge (NPOP/PGS/USDA) + expiry + verified filter (3.5h) · cert-education bar + guides (2.5h)
- **D35** product detail w/ Product JSON-LD + comparison-lite (2.5h) · where-to-buy + store locator (3h)
- **D36** RFQ I: posting + category×geo matching (3.5h) · brand RFQ inbox — threat: cross-competitor leakage → scoping reviewed [YOU] (3h)
- **D37** RFQ II: two-sided ratings + lead-credit gating (3h) · brand dashboard (products/certs/analytics) (3h)
- **D38** homepage per mockup (3h) · search/filters + cross-site coin hooks verified (2.5h)
- **D39** PWA parity (2.5h) · category×geo ISR + sitemaps + Product markup (3h) · [BG] 100+ brands seeded
- **D40** E2E: browse→where-to-buy, RFQ round-trip, cert flow (3h) · device+vernacular matrix (2.5h)
- **D41** adversarial RFQ/cert/dashboard (3h) · load + WAF (2h)
- **D42** launch prep (5h) · **D43** buffer · **D44 — 🌿 ORGANICSTORE.IN LAUNCH ★** promote, v1.1.0-organic.

## ■ BLOCK 6 — AGRI.IN HUB (D45–62)
- **D45** location-first home + search/mic shell + eco-switcher (3h) · Today strip: weather/mandi/alert cards (3h)
- **D46** 34-tile category grid, 5 groups, icon+EN+vernacular, zero hamburgers (3h) · honest "coming soon" landings, self-noindexed, notify-me (2.5h)
- **D47** weather: Open-Meteo hyperlocal + 7-day + severe banners + caching (3h) · pages/widgets/alert subs (2.5h)
- **D48** mandi I: Agmarknet worker + 90-day backfill + quality checks (3.5h) · commodity×market×state ISR + Dataset JSON-LD (3h)
- **D49** mandi II: trends + price alerts (3h) · commodity×state SEO pages (2.5h)
- **D50** news: RSS ingest + curation + attribution + state tags (3h) · feed UI + bookmarks (2.5h) · [BG] 40 knowledge drafts
- **D51** knowledge CMS (Claude-assist + human gate, i18n) (3.5h) · guides w/ FAQPage JSON-LD (2.5h)
- **D52** hub directory UI + sponsored pins (3h) · **helpline band + offline click-to-call page** + schemes static v0 (3h)
- **D53** assistant I: pgvector RAG + read-only mandi/weather tools (4h) · chat UI EN/TA/HI (3h)
- **D54** assistant hardening: injection defense, scope guard, output filters, tier limits, red-team run (3.5h) · Ask-AI entry on all sites (2h) · [YOU] personal sign-off (1.5h)
- **D55** advertiser self-serve: campaign→target→creative→pay→approve→live (3.5h) · slot rendering + advertiser analytics (3h)
- **D56** coins full activation (all earn + burn) (3h) · coins center + referral share (2.5h)
- **D57 ★** unified notification center + federated search (dairy/organic cards on hub) (3h) · switcher polish + nudges (2h) · [YOU] one-identity walkthrough (1.5h)
- **D58** PWA parity + hub sitemap architecture + Lighthouse sweep (5.5h)
- **D59** full QA (6h) · **D60** adversarial hub audit (assistant, ads money path) + full k6 (5.5h) · **D61** launch prep + restore drill #3 (5.5h)
- **D62 — 🌾 AGRI.IN v1 LAUNCH ★** promote, v1.2.0-agri. Three platforms, one AgriID.

## ■ BLOCK 7 — STAGE B: INPUTS & EQUIPMENT (D63–80) — 25% ops budget
- **D63–64** spec-schema admin builder + schema-driven filters/facets/sheets/comparison (6h) · bulk import (validate/dedupe/stage) + Console v2 schema forms (6h)
- **D65–66** vertical×geo ISR factory + noindex-until-populated + auto-sitemaps (5h) · internal-link mesh; [BG] SEO-copy pipeline + spot-check queue (5h)
- **D67** SEEDS vertical end-to-end, frozen as VERTICAL-TEMPLATE (schema/landing/filters/products/100+ companies) (7h)
- **D68–72** template rollout ~1.5/day: Fertilizers · Crop-protection (CIB&RC, toxicity bands, [YOU] all safety copy) · Implements/tools · Harvesters/machinery · Drip (quote form) · Pumps/solar (subsidy flags) · Drones (DGCA, service providers) · quality sprint + claim campaign + coin rewards
- **D73–76** tractor flagship: comparison browse + battle cards (5.5h) · EMI calc + price explorer (5h) · dealer locator + test-drive leads (5h) · buying guides EN/TA/HI (4h)
- **D77–78** ads v2: takeovers + sponsored products + vertical×geo×role×language targeting (5h) · advertiser analytics + rate cards + brand outreach kit (4h)
- **D79** import-pipeline adversarial + index-coverage check (5h)
- **D80 ★ GATE 4:** 8 verticals · 500+ companies · pages indexing · tractor UX · first paid campaigns. Promote.

## ■ BLOCK 8 — STAGE C: SERVICES & TRUST (D81–95)
- **D81–82** booking-inquiry engine (services/slots/lifecycle/notifications) (5.5h) · provider calendar-lite + completion reviews + reminders (5.5h)
- **D83** soil + water test labs (menus, pickup booking, report-to-account) (5.5h) · **D84** agritech directory + FPO profiles (4.5h)
- **D85–86** loans: lender directory + product tables + EMI (5h) · eligibility-lite lead → consent-first routing (5h) · [YOU] money-copy review
- **D87** consulting + vet (profiles, bookings, emergency flag) (5.5h)
- **D88–89** insurance: PMFBY guides + comparisons + agent routing (5h) · claim guides + state deadline alerts (4.5h)
- **D90** warehouses (WDRA, space requests) + transport (load↔vehicle) (5.5h)
- **D91–92** schemes flagship: dataset + verified-sourcing + last-verified stamps (4h) · **eligibility wizard** (5h) · [YOU] every scheme verified vs official source (3h)
- **D93** cert info + carbon (guides + directories + interest leads) (5h) · **D94** data-engine hardening + Stage-C adversarial (6h)
- **D95 ★ GATE 5:** wizard live on verified data · booking round-trips · loan/insurance routing. Promote.

## ■ BLOCK 9 — STAGE D: COMMUNITY & CONTENT (D96–103)
- **D96–97** forum + Q&A mode + accepted answers + coin rewards (10h) · **D98** moderation (reports/limits/AI pre-classifier→human arbiter) + expert flair (5.5h) · **D99** forum SEO + digests (4.5h) · **D100** webinars/events full (5.5h) · **D101–102** content velocity: calendar (vertical×season) + tri-language pipeline + Kharif/Rabi packs (9h mostly [BG]) · **D103 ★ GATE 6.** Promote.

## ■ BLOCK 10 — STAGE E: CLASSIFIEDS & MATCHMAKING (D104–118) — highest fraud surface, last by design
- **D104–105** classifieds engine + fraud core (phone-verified posting, image checks, dedup, velocity, reports, interstitials, reveal caps DPDP-logged) (10.5h)
- **D106** unified moderation console + AI pre-pass + audit trail (5.5h)
- **D107–108** livestock (schemas incl. vaccination/yield, species×district, safety checklists, badges, SOP, FPO-seeded) (10h) · [YOU] no-payment framing verified
- **D109–112** land map-first: MapLibre cluster+draw (5.5h) · schema + flags + verified posting (5h) · trust framework (disclaimers, fraud detection, takedowns) (5h) · alerts + saved search + district/taluk SEO (5h)
- **D113–116** labour vernacular flagship: worker profiles (5h) · job posts (wage mandatory) + distance match (5h) · icon-first low-literacy UX + voice-notes (5.5h) · match loops + [YOU] safety review (5h)
- **D117** trade leads (business-verified gate) + land↔lessee matching (5h)
- **D118 — 🌾 FULL LAUNCH ★** final full-stack security audit (3h) · full k6 + restore drill #4 + runbooks (2h) · all tiles real (1h). Promote, tag v2.0.0.

---

# PART 4 — CI MERGE GATES (into dev, enforced from D4)
lint/typecheck · unit+API tests · migration up **and** down · gitleaks secret scan · dependency audit (fail high) · offset-pagination ban · import-linter module boundaries · **public-route audit vs public_routes.txt** · **Lighthouse ≥90 throttled-3G on affected templates** · E2E for touched journeys · ≤10 min warm. Sensitive-path PRs: + line-by-line human review + adversarial audit note. **Gates are never soft-disabled; removing one requires editing protected workflow files, visible in review.**

# PART 5 — LAUNCH CHECKLIST (D32, D44, D62, D118 — plus dev→main promotion)
**Security:** adversarial audit clean · OWASP · dep audit · WAF+rate limits live · secrets rotated · restore drill <7 days · kill switches tested · public_routes.txt manually reviewed.
**SEO:** all public pages ISR/SSR · JSON-LD validating · sitemaps submitted · thin pages noindexed · redirects live · Lighthouse ≥90 top-10 templates.
**Legal/privacy:** privacy+terms+lead-gen disclaimers+coins T&C live · DPDP consent/export/delete verified · PII absent from sampled logs.
**Quality:** E2E green · device matrix (low-end Android/iOS/desktop) · vernacular QA · low-data mode.
**Ops:** DNS+rollback rehearsed · monitors/alerts/on-call · hotfix lane · support inbox.
**Data:** seed live · translations complete · last-verified stamps current.

# PART 6 — RISK LEDGER
| Risk | Mitigation |
|---|---|
| **DLT still unfiled by D12** | Mock driver unblocks dev, but D32 slips 1:1 with filing delay. Reminders wired at D7/D10; verify real SMS at D30. |
| **Razorpay unfiled by D18** | Billing behind feature flag; fallback = free-tier launch, flip flag post-KYC. |
| Burnout | Day-7 rest is schedule-critical; weekly buffer half-days; specs make any day resumable. |
| Live-ops creep (D33+) | 20–25% budgeted; overflow eats weekly buffer — never gates. |
| Classifieds fraud | Launched last; kill switches per vertical; reveal caps. |
| Scope temptation | New ideas → registry backlog, never the current block. |
| Stale branches (solo git) | Same-day merge rule; no branch survives overnight without written reason. |

**Slippage rule:** a block slipping >2 days cuts content inside that block — never security gates, never AgriID/AgriCoins, never sensitive-code review, never a CI merge gate.

---

# PART 7 — WHERE YOU ARE RIGHT NOW + NEXT ACTIONS
✅ Domains ready · ✅ v5 master locked · ✅ Sprint 0 spec pack in hand · ✅ VS Code + Claude extension configured · ⏸ DLT & Razorpay held (deadlines D10–12 / D18 wired into schedule).

1. `git checkout -b dev && git push -u origin dev` · protect main+dev · set dev as default branch.
2. CLAUDE.md at repo root: Constitution §0.1 + git rules §0.2 + never-do list. First commit.
3. Branch `feat/d01a-monorepo` off dev → paste SPEC D01-A. Second window: `feat/d01b-fastapi-skeleton` → SPEC D01-B.
4. Day 1 is done when the 401-by-default test is green and both PRs are merged to dev.
5. D02→D05, one spec per day. At GATE 1 (D5): promote dev→main, tag v0.1.0, request the Sprint 1 spec pack (D06–D14, AgriID + AgriCoins).

**Launch calendar:** 🥛 D32 (~wk 6) · 🌿 D44 (~wk 8) · 🌾 D62 (~wk 11) · Full D118 (~wk 20).