# SPRINT 0 SPEC PACK v2 — D01–D05 PROMPTS (Design System Spec v1 integrated)
# Supersedes v1 pack. One spec per fresh Claude session. Every spec ends with PR → dev.
# Prereqs already done: repo + CLAUDE.md + dev branch + protections + docs committed
# (docs/design-system.md, docs/design-reference/preview_frontend.html).

═══════════════════════════════════════════════════════════════
# PART A — SPRINT-LEVEL EXECUTION SCHEDULE (the whole run, one page)
═══════════════════════════════════════════════════════════════

| Sprint / Block | Days | Delivers | Gate → promote dev→main, tag |
|---|---|---|---|
| **Sprint 0 — Foundation** (this pack) | D1–5 | Monorepo, SecureRouter, **design system per Spec v1**, one-way doors, CI gates, observability+backup drill | GATE 1: clone→run <15 min; insecure endpoint fails CI → **v0.1.0** |
| Sprint 1 — AgriID + AgriCoins | D6–14 | OTP (mock driver), OAuth2/PKCE SSO, profiles, RBAC, audit, notify, coins ledger | GATE 2: SSO 3 domains; 10k awards zero drift → **v0.2.0** |
| Sprint 2 — Shared core | D15–22 | Directory+coverage, registry/spec-schemas, media, reviews, leads, search, billing(flagged), ads v1, admin | GATE 3: register→claim→subscribe→lead E2E → **v0.3.0** |
| Sprint 3 — Milk.in | D23–32 | Pincode-first discovery, vendor profiles/dashboard, need-posting leads, PWA, SEO, hardening | 🥛 **LAUNCH D32 → v1.0.0-milk** |
| Sprint 4 — OrganicStore.in | D33–44 | Catalog+certs, where-to-buy, B2B RFQ, brand dashboard, PWA/SEO, hardening | 🌿 **LAUNCH D44 → v1.1.0-organic** |
| Sprint 5 — Agri.in hub | D45–62 | Home+34-tile grid, weather, mandi, news, knowledge, helpline, AI assistant, ads self-serve, coins full, unification | 🌾 **LAUNCH D62 → v1.2.0-agri** |
| Stage B — Inputs & equipment | D63–80 | Schema builder, SEO factory, 8 verticals, tractor UX, ads v2 | GATE 4 |
| Stage C — Services & trust | D81–95 | Booking engine, labs, loans, insurance, warehouses, transport, schemes wizard | GATE 5 |
| Stage D — Community & content | D96–103 | Forum+Q&A, webinars, content velocity | GATE 6 |
| Stage E — Classifieds & matchmaking | D104–118 | Livestock, land map-first, labour vernacular, trade leads | 🌾 **FULL LAUNCH D118 → v2.0.0** |

External clocks: **DLT file by D10–12** · Razorpay KYC by D18 (billing behind flag until then).
Git rhythm every spec: `git checkout dev && git pull` → `feat/dXX?-name` → build → PR → dev → merged same day.

═══════════════════════════════════════════════════════════════
## SPEC D01-A — MONOREPO SCAFFOLD (Track A, ~3h) · branch: feat/d01a-monorepo
═══════════════════════════════════════════════════════════════
CONTEXT: Repo `agri-ecosystem` (Windows dev machine, Node 20, pnpm 9). Building the Turborepo monorepo
hosting 5 Next.js 15 apps + shared packages. CLAUDE.md Constitution and docs/design-system.md already
committed — obey both. Work on branch feat/d01a-monorepo off dev; finish with a PR targeting dev.

DO:
A. Turborepo + pnpm workspaces:
   apps/web-milk, apps/web-organic, apps/web-agri, apps/web-id, apps/web-admin
   packages/ui, packages/auth-client (stub), packages/config, packages/types
B. Each app: Next.js 15 App Router, TypeScript strict, Tailwind; placeholder route rendering app name;
   `data-theme` attribute already set on the root layout per app: theme-agri | theme-milk | theme-organic
   (web-id and web-admin use theme-agri) — the theme hook Design Spec §1.1 plugs into on D02.
C. packages/config: base tsconfig, eslint, and a tailwind preset STUB exporting an empty theme object
   (D02 fills it with Design Spec tokens).
D. packages/types: wired for OpenAPI-generated types (`pnpm gen:types` placeholder).
E. Root scripts: dev/build/lint/typecheck via turbo, caching configured. .gitignore, .nvmrc, README quickstart.

DO NOT: no UI beyond placeholders (D02 owns design) · no backend/ (D01-B) · no auth logic in auth-client ·
no dependency not required above · no commits to dev/main directly.

NON-NEGOTIABLES:
1. `pnpm i && pnpm dev` boots 5 apps on distinct ports (3000–3004), warnings-as-errors clean.
2. TS strict everywhere, zero `any`.
3. All packages scoped `@agri/*`.
4. Second `pnpm build` is a turbo cache hit.

THREAT MODEL: none at runtime; no secrets/real domains in code.
ASSUMPTIONS TO CONFIRM: ports 3000–3004 in app order listed; pnpm 9.

DEFINITION OF DONE: fresh clone → quickstart works; lint/typecheck/build green; PR opened → dev with
summary of layout decisions; merged same day. Conventional commit: `feat(d01a): monorepo scaffold`.

═══════════════════════════════════════════════════════════════
## SPEC D01-B — FASTAPI SKELETON + SECURE ROUTER (Track B, ~3.5h) · branch: feat/d01b-fastapi-skeleton
═══════════════════════════════════════════════════════════════
CONTEXT: backend/core — FastAPI modular monolith, **Python 3.13**, Pydantic v2, SQLAlchemy 2 async.
Backend truth lives in Docker (Dockerfile pins 3.13); host Python is tooling only. Modules talk ONLY via
public service interfaces or the event bus. This spec builds the skeleton AND the Constitution's security
machinery. Branch feat/d01b-fastapi-skeleton off dev; PR → dev.

DO:
A. Layout: backend/core/{main.py,settings.py} · modules/{identity,coins,directory,leads,content,
   market_data,ads,notify,search,billing,ai}/(router.py, service.py, models.py empty) ·
   shared/{db.py,cache.py,events.py,storage.py,telemetry.py,security.py}.
B. settings.py via pydantic-settings; .env.example with every var name, NO real values.
C. **SecureRouter** (shared/security.py): APIRouter subclass — every route auto-gets (1) auth dependency
   stub (401 until identity lands), (2) Redis-backed rate-limit dependency (in-memory dev fallback),
   (3) response-model enforcement. Only bypass: `public=True` param, which registers the route in a
   startup public-route registry that is logged on boot.
D. /health and /health/deep (public) endpoints.
E. Dockerfile (multi-stage, non-root, python:3.13-slim) + docker-compose.dev.yml: api, postgres:16,
   redis:7, meilisearch, minio — healthchecks + named volumes.
F. Ruff + mypy strict; pytest with THE test: a route registered without `public=True` returns 401.
G. import-linter contract: modules cannot import each other's internals — build fails on violation.

DO NOT: no real JWT/auth logic (D08–09) · no DB tables/Alembic (D03) · no secrets anywhere ·
no cross-module imports · no direct pushes to dev/main.

NON-NEGOTIABLES:
1. Thoughtless new endpoint = PRIVATE + RATE-LIMITED, proven by the pytest.
2. import-linter green and enforced.
3. Container non-root; `docker compose up` = healthy stack, one command.
4. mypy strict passes; shared/ fully typed.

THREAT MODEL: future sessions forgetting auth on an endpoint — this spec makes that failure impossible.
ASSUMPTIONS TO CONFIRM: modular monolith per ADR-A1; MinIO stands in for R2 locally.

DEFINITION OF DONE: compose stack healthy; 401-default test green; boot log shows public routes ==
[/health,/health/deep]; PR → dev merged. `feat(d01b): fastapi skeleton + secure router`.

═══════════════════════════════════════════════════════════════
## SPEC D02 — DESIGN SYSTEM PER SPEC v1 (~6h) · branch: feat/d02-design-system
═══════════════════════════════════════════════════════════════
CONTEXT: packages/ui + packages/config for all 5 apps. **THE BINDING REFERENCES ARE IN-REPO:
docs/design-system.md (tokens + component anatomy + 8 UX laws) and
docs/design-reference/preview_frontend.html (approved mockup).** Read BOTH before writing any code.
The deliverable bar: a demo route whose components are visually indistinguishable from the mockup.
Audience spans illiterate to affluent users — icon-first, vernacular-labeled, ≥44px targets.

DO:
A. **Tokens — exact values from design-system.md §1** into the packages/config tailwind preset:
   three `data-theme` themes (agri #2C6E35/#1E4E26/#E8F2E6/#E9A61C · milk #2563A8/#174A85/#E9F1FA/#E9A61C ·
   organic #4A6B2A/#35511C/#EFF3E4/#B5541C), shared neutrals (--ink #1D2A20, --sub, --paper, --page-bg
   #E9EBE2, --card, --line #E2E7DA), semantics (--call #1E9E4A, --wa, coins gold, alert, helpband #153A1D,
   badge trios, rating #C77700), radius scale (16/12/99/18/14), header-gradient utility
   (160deg brand-deep→brand), focus ring (3px accent, offset 2).
B. Fonts: Bricolage Grotesque (display 600/800) + Public Sans (body) + Noto Sans Tamil/Devanagari
   subsets; `.vern` utility (0.78em/500/.85 opacity/own line).
C. ShadCN init; build the 18 components MATCHING design-system.md §2 anatomy exactly:
   Button, Card, **CategoryTile** (52px tinted icon square 14px-radius + 12px/700 EN + vern line,
   min-h 104px, hover lift + brand border), **CallButton/WhatsAppButton** (exact color recipes, flex-1,
   emoji-prefixed), **Badge** (verified/sponsored/cert exact palettes; sponsored always "★ Sponsored"),
   **SearchBar** (floating white bar, 46px accent mic right-most, cam slot, hint-line slot),
   **PincodeInput** (6-digit numeric, .15em tracking, brand Find button, GPS glass pill),
   **BottomNav** (5 slots, raised 46px brand-circle center "Ask AI" −22px w/ 4px white ring),
   **ListingCard** (badge row → 56px icon square + 15.5/800 title + meta → price-tag → action row),
   RatingStars ("★ 4.7" text pattern #C77700/800), LangSwitcher ("🌐 EN · த · हि" glass pill),
   LocationPill, CoinsPill (gold, 🪙), Modal, Toast, EmptyState, Skeleton (fixed dims, CLS 0).
D. Composite patterns as exported layout components: HeaderStack (gradient + topbar + searchband),
   PincodeHero, TodayStrip (+alert variant), CategoryGroup (uppercase hairline label + auto-fill grid),
   HelplineBand (glowing call button), BigCtaTile (gradient), TypeFilterRow, ProductCard, CertBar, EcoStrip.
E. i18n: next-intl in all 5 apps, en/ta/hi catalogs for component strings, vernacular font loading.
F. **SEO primitives** (packages/ui/seo): typed <JsonLd> builders (LocalBusiness/Product/FAQPage/
   BreadcrumbList/Dataset), MetaBuilder, breadcrumb generator, canonical helper, <NoIndex> +
   shouldNoIndex(contentCount). Server components — zero `use client`.
G. Demo route in web-agri: all 18 components + all composites, rendered per theme (switchable),
   in all 3 locales. Screenshot each theme → docs/design-reference/baseline/ (visual-regression baseline).

DO NOT: no page/screen builds beyond the demo route · **no raw hex in component code — tokens only**
(add an eslint rule or grep-check script banning hex literals in apps/ and packages/ui/) ·
no hardcoded site names/colors in components · no client-side data fetching in this package ·
do not "simplify away" gradients, glass pills, or hover lifts — they are spec.

NON-NEGOTIABLES:
1. Demo components visually indistinguishable from the mockup reference (side-by-side check).
2. Every interactive element ≥44px and keyboard-operable; focus ring per spec; reduced-motion respected.
3. CategoryTile renders icon+EN+vernacular in all 3 locales without layout break.
4. JsonLd builders typed — invalid shapes fail typecheck; SEO components are server-only.

THREAT MODEL: visual drift toward library defaults (baseline screenshots kill it); CLS from unsized media.
ASSUMPTIONS TO CONFIRM: emoji icons are v1-official per design spec §4; data-theme switching mechanism.

DEFINITION OF DONE: demo route matches mockup; Lighthouse a11y ≥95 on demo; hex-ban check green;
baseline screenshots committed; PR → dev merged. `feat(d02): design system per spec v1`.

═══════════════════════════════════════════════════════════════
## SPEC D03 — DATA FOUNDATION: ONE-WAY DOORS (~6h) · branch: feat/d03-data-foundation
═══════════════════════════════════════════════════════════════
CONTEXT: Encode the Constitution's one-way doors as reusable machinery. Postgres 16, SQLAlchemy 2 async,
Alembic. **Use plan mode first** — present the approach before writing. Branch off dev; PR → dev.

DO:
A. Alembic multi-schema (identity, coins, directory, leads, content, market, ads, notify, billing, geo);
   one version tree; CI-runnable upgrade-head + downgrade-1 script.
B. Base mixins (shared/db.py): UUIDv7 PK, created_at/updated_at timestamptz UTC server defaults,
   soft-delete w/ default filter, UGCMixin(moderation_status ENUM default 'pending').
C. Customized migration template auto-including mixin columns + mandatory "-- THREAT/NOTES:" block.
D. Cursor pagination: keyset paginate() + typed Page[T] w/ next_cursor; **lint contract banning `.offset(`**
   with a test fixture proving the ban fires.
E. `owned_by(query, user)` ownership helper + service-layer convention doc.
F. Slug infra: ImmutableSlug mixin (write-once guard) + redirects table + 301 middleware.
G. JSONB TranslatedString type ({"en","ta","hi"}) + accessors.
H. Redis Streams event bus: publish/consume w/ consumer groups + dead-letter + round-trip test.
I. Feature-flag table + cached read API + seed flags (billing_enabled=false, ads_enabled=false).
J. geo schema v1: states/districts/pincodes(+centroids); loader from open datasets; Tamil Nadu loaded,
   pincode→district+centroid test passing; source URLs listed in PR body for review.

DO NOT: no module business tables (identity starts D06) · no OFFSET anywhere incl. admin · no naive
datetimes · no UUIDs in URL-facing helpers (slugs are public identifiers).

NON-NEGOTIABLES: 1. every migration downgrades in CI · 2. mixin model = UUIDv7+UTC+soft-delete with zero
extra code · 3. paginate() is the only list mechanism, ban enforced · 4. TN geo lookups correct in tests.

THREAT MODEL: data-integrity drift (timezones, mutable slugs breaking SEO, offset collapse at scale) —
this day makes those bugs unwritable.
ASSUMPTIONS TO CONFIRM: uuid library choice; geo dataset source.

DEFINITION OF DONE: demo migration using all mixins up+down in CI; paginate/redirect/event-bus tests green;
TN counts in PR; PR → dev merged. `feat(d03): data foundation one-way doors`.

═══════════════════════════════════════════════════════════════
## SPEC D04 — CI/CD + MERGE GATES (~6h) · branch: feat/d04-ci-gates
═══════════════════════════════════════════════════════════════
CONTEXT: GitHub Actions enforcing the Constitution on every PR → dev. Staging deploys from dev to the
hardened VPS via SSH; SOPS-encrypted secrets (age key held offline by the human). Plan mode first.

DO:
A. PR pipeline: pnpm lint+typecheck+vitest+build (turbo-cached) · ruff+mypy+pytest · alembic up+down vs
   service Postgres · import-linter · offset-ban check · **hex-literal ban in apps/+packages/ui (design
   tokens rule)** · gitleaks secret scan · dependency audit (fail high).
B. **Public-route audit gate**: CI boots API, diffs registry vs committed public_routes.txt — new public
   route requires editing that file in the PR.
C. **Lighthouse CI**: affected app templates, mobile + throttled-3G, assert perf ≥90 / a11y ≥95 / SEO ≥95;
   budget file committed. Include the D02 demo route.
D. Docker image build+push (api + apps) tagged by sha on merge to dev.
E. Staging deploy job (manual approval, from dev): SSH → pull → compose up → smoke (/health/deep + one
   page per app) → auto-rollback on smoke failure.
F. SOPS wiring + key-handling README.
G. Branch protection verification doc: main & dev require PRs + green checks; conventional commits enforced.

DO NOT: no plaintext secrets in workflows/logs · no auto-deploy on merge (manual approval; prod doesn't
exist yet) · no cache-skipping — pipeline must stay <10 min warm or it gets bypassed under pressure.

NON-NEGOTIABLES: 1. undeclared public route FAILS CI · 2. Lighthouse regression <90 FAILS CI ·
3. irreversible migration FAILS CI · 4. raw hex in UI code FAILS CI · 5. pipeline ≤10 min warm.

THREAT MODEL: CI-log secret leakage; deploy-key theft (deploy-scoped, IP-restricted); gate erosion under
deadlines (gates live in protected workflow files — removal is visible in review).
ASSUMPTIONS TO CONFIRM: GitHub-hosted runners; staging = same VPS, separate compose project.

DEFINITION OF DONE: demo PR all-green; deliberately-bad PR (public route + offset + hex + fake secret)
shows four red gates; one staging deploy executed end-to-end; PR → dev merged. `feat(d04): ci gates`.

═══════════════════════════════════════════════════════════════
## SPEC D05 — OBSERVABILITY + BACKUPS + GATE 1 (~5.5h) · branch: feat/d05-observability
═══════════════════════════════════════════════════════════════
CONTEXT: If it isn't measured it doesn't exist; a backup without a restore drill isn't a backup.
This day closes Sprint 0 at GATE 1 and triggers the first dev→main promotion (tag v0.1.0).

DO:
A. Sentry backend (FastAPI, release tags) + all 5 apps; source-map upload in CI.
B. Structured JSON logging: request_id middleware FE→BE; **PII-scrub filter** (phone/email redaction)
   with a unit test proving [REDACTED] output; env-driven levels.
C. pg_stat_statements + slow-query log (>200ms) + p95/error-rate counters (Prometheus format endpoint);
   Netdata on VPS for host metrics.
D. Uptime Kuma monitors (API health, each app, staging) + phone/email alert channel.
E. Backups: nightly pg_dump (custom format, age-encrypted) + WAL → R2; 30-day lifecycle;
   scripts/restore.sh restoring to a scratch DB.
F. **RESTORE DRILL #1 — actually executed on the VPS, timed**; runbook docs/runbooks/backup-restore.md
   with measured RTO.
G. docs/adr/: one ADR per Constitution decision, each stating one-way/two-way door + reversal cost.
H. Per-module CLAUDE.md files from a template (boundary rules, never-do, spec pointer, design-spec pointer).

DO NOT: no request-body logging on auth/PII routes · no Prometheus/Grafana stack yet (Netdata+Kuma
right-sized; swap path in ADR) · **do not mark done without the drill actually run**.

NON-NEGOTIABLES: 1. PII-redaction test green · 2. restore drill executed+timed+documented, not simulated ·
3. every ADR exists · 4. request_id traces app→API→log in a demo.

THREAT MODEL: silent backup rot (drill kills it); PII in logs (filter+test); alert fatigue (actionable only).
ASSUMPTIONS TO CONFIRM: R2 credentials ready; age keypair generated and stored offline.

DEFINITION OF DONE: **GATE 1 — fresh clone → running stack <15 min (timed); the deliberately-insecure
endpoint fails CI; drill runbook committed with real timings.** PR → dev merged → **human promotes
dev→main, tags v0.1.0** → request Sprint 1 spec pack (D06–D14: AgriID + AgriCoins).