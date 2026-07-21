# D21 — Ads Engine v1 + Ops Console — Design

**Date:** 2026-07-21 · **Branch:** `feat/d21-ads-ops` · **PR target:** `dev`
**Source spec:** docs/Sprint/Sprint2 spec pack d15 d22.MD (SPEC D21)

## Context

Ads are the neutral monetization: labeled sponsored placements in dedicated
slots, never pay-to-rank of organic results. v1 is internal/admin-operated
(D55 brings advertiser self-serve). The Ops Console unifies moderation
(D16 claims + D18 reviews + D21 creatives) and feature-flag switches in
web-admin.

Existing groundwork this design builds on (verified in the tree):

- `modules/ads/` scaffold, `ads` schema, and the `ads_enabled` flag
  (seeded false in 0003) already exist. `ads_router` is already mounted.
- No table-partitioning precedent exists — impressions/clicks are the
  codebase's first partitioned tables.
- Four structurally identical pending→approve/reject flows exist today
  (claims, verifications, reviews, catalog products), each duplicating
  `_require_role`, `_publish_best_effort`, and page schemas; web-admin's
  `QueueSection<T>` was forked (`reviews-manager.tsx`), not shared.
- Cross-module imports are banned (import-linter), so the unified queue
  uses the DI-registry style of `shared/lookups.py` /
  `register_principal_resolver`.

Decisions taken during brainstorming:

- **Queue shape:** backend source registry (`shared/moderation.py`
  protocol + per-module registered sources) fronted by one ops admin
  router and ONE shared web-admin queue component. Not a materialized
  queue table; not frontend-only unification.
- **Serving scope:** serving API + `<SponsoredAd>` component + one live
  slot on web-agri's directory browse page (flag-gated).
- **Flag RBAC:** moderation is staff + super_admin; flag/kill-switch
  toggles are **super_admin only**, every change audited.
- Sources registered in v1: `claim`, `verification`, `review`,
  `creative`. Catalog products keep their existing route and register
  later (one-file change by design).

## 1. Schema — `ads` (one alembic migration, `0022_ads_v1.py`)

Per-table grants only (0019/0021 precedent). Mandatory `# -- THREAT/NOTES:`
block. Linear after 0021.

**`ads.campaigns`**

| column | type | notes |
|---|---|---|
| id | UUIDv7 PK | |
| advertiser_business_id | UUID NOT NULL, indexed | no cross-schema FK (module independence); existence validated at creation via the `shared.lookups` business resolver |
| name | TEXT NOT NULL | |
| status | TEXT CHECK ('draft','active','paused','archived') | default 'draft' |
| budget_display | TEXT | display-only; no money math in v1 |
| flight_start | DATE NOT NULL | |
| flight_end | DATE NOT NULL | CHECK flight_end >= flight_start |
| created/updated | TimestampMixin | |

**`ads.creatives`**

| column | type | notes |
|---|---|---|
| id | UUIDv7 PK | |
| campaign_id | UUID FK → ads.campaigns, indexed | |
| media_keys | JSONB NOT NULL default '[]' | list of storage keys; uploads go through the shared D16/D17 media helper (presign + pixel guard) |
| copy | JSONB NOT NULL | `{en?:{title,body}, ta?:{...}, hi?:{...}}`; `en` required; plain text only, escaped at render |
| target_url | TEXT NOT NULL | validated: http/https scheme only, ≤ 2048 chars; re-checked at serve time |
| moderation_status | UGCMixin | defaults 'pending' → unified queue |
| created/updated | TimestampMixin | |

**`ads.placements`**

| column | type | notes |
|---|---|---|
| id | UUIDv7 PK | |
| campaign_id | UUID FK → ads.campaigns, indexed | |
| slot_key | TEXT NOT NULL | validated in code against `SLOT_KEYS = {"directory_browse"}` (v1); no slots table |
| geo_target | JSONB NOT NULL default '{}' | `{state?: lgd_code, district?: lgd_code, pincodes?: [text]}`; `{}` = serve everywhere |
| weight | SMALLINT NOT NULL default 1 | share-of-voice; CHECK weight >= 1 |
| status | TEXT CHECK ('active','paused') | default 'active' |
| created/updated | TimestampMixin | |

**`ads.impressions`** and **`ads.clicks`** — identical shape, high-volume,
append-only, `PARTITION BY RANGE (occurred_at)` with daily partitions.

| column | type | notes |
|---|---|---|
| id | UUIDv7 | PK is `(id, occurred_at)` — partition key must be in the PK |
| placement_id | UUID NOT NULL | no FK (write-path speed; rows are raw log) |
| creative_id | UUID NOT NULL | |
| slot_key | TEXT NOT NULL | |
| viewer_hash | TEXT NOT NULL | daily-rotating hash, see §3 |
| pincode | TEXT NULL | request context for later analysis |
| occurred_at | TIMESTAMPTZ NOT NULL | partition key |

Index on `(placement_id, occurred_at)` for the stats query.

Append-only both ways (standing rule: immutable tables get triggers, not
just REVOKE):

- `BEFORE UPDATE OR DELETE` trigger raising an exception, created on the
  partitioned parent (row triggers propagate to all partitions, PG16).
- `GRANT SELECT, INSERT` to `app_rt`; explicit `REVOKE UPDATE, DELETE`.

**Partition automation — two belts so inserts never fail on a new day:**

1. The migration pre-creates daily partitions for `today .. today+7` and
   a `DEFAULT` partition per table (backstop: an insert past the last
   daily partition lands in DEFAULT instead of erroring).
2. `modules/ads/maintenance.py::ensure_partitions(days_ahead=7)` —
   idempotent (`CREATE TABLE IF NOT EXISTS ... PARTITION OF ...`), run by
   the ads worker tick (§3) using `DATABASE_ADMIN_URL` (partition DDL is
   owner work; `app_rt` has no CREATE — by design).

Other grants: campaigns/creatives/placements get
`GRANT SELECT, INSERT, UPDATE, DELETE` to `app_rt` (normal mutable rows),
each as an explicit per-table statement.

## 2. Unified moderation queue — `shared/moderation.py` + `modules/ops`

The sprint's convergence point. One abstraction, DI-registered, so D96+
(forum) and Stage E (classifieds) extend it by registering a source.

### 2.1 `shared/moderation.py`

```python
@dataclass(frozen=True)
class ModItem:
    type_key: str          # "claim" | "verification" | "review" | "creative"
    id: UUID
    created_at: datetime
    title: str             # one-line, list rendering
    summary: str           # short body for the card
    payload: dict          # type-specific extras (media keys, rating, url…)

@dataclass(frozen=True)
class ModDecision:
    item: ModItem                       # post-decision snapshot
    events: list[PendingEvent]          # (stream, type, payload) captured
                                        # BEFORE commit, published after

class ModerationSource(Protocol):
    type_key: str
    async def count_pending(self, session) -> int: ...
    async def list_pending(self, session, cursor, limit) -> Page[ModItem]: ...
    async def approve(self, session, item_id, actor_user_id, note) -> ModDecision: ...
    async def reject(self, session, item_id, actor_user_id, note) -> ModDecision: ...

register_moderation_source(source)   # startup wiring (main.py)
get_source(type_key) / iter_sources()
reset_moderation_sources()           # test hook (joins _reset_state)
```

Source contract (mirrors the proven decision choreography):

- `approve`/`reject` run the owning module's existing FOR UPDATE +
  status-check decision service, call `audit()` **in the same
  transaction** (existing action strings preserved), and capture every
  post-commit payload before returning (ORM attributes expire on commit).
- Sources never commit. The ops router owns the single
  `commit → best-effort publish(decision.events)` sequence — one shared
  implementation instead of a fifth `_publish_best_effort` clone.
- Conflict semantics unchanged: already-decided → 409 (existing
  domain errors mapped by the ops router).

Sources registered at startup in `main.py` (which already imports every
module — the sanctioned wiring point):

- `modules/directory/moderation_sources.py` — `claim`, `verification`
  (wrap `claims.py` services), `review` (wraps `reviews_service.moderate`
  + `recompute_aggregate`; approve captures the `review.approved` event
  exactly as the current router does).
- `modules/ads/moderation_sources.py` — `creative` (approve/reject flips
  `moderation_status` under FOR UPDATE; emits `creative.approved`/
  `creative.rejected` on the `ads` stream for future consumers; **no**
  EVENT_ROUTES entry — no notification in v1, deliberate).

Existing `/admin/directory/claims|verifications` and `/admin/reviews`
routes remain for API back-compat but web-admin stops calling them (§4).

### 2.2 `modules/ops` (new module)

Added to `main.py` `MODULE_ROUTERS` and to both import-linter contracts.
Imports `shared` only. Role gate: a `require_role(request, *allowed)`
helper is added to `shared/security.py` (ops + ads use it; existing
routers keep their local copies — D22 cleanup candidate, out of scope).

| route | gate | behaviour |
|---|---|---|
| `GET /admin/moderation/summary` | staff, super_admin | `{type_key: pending_count}` across `iter_sources()` |
| `GET /admin/moderation/queue?type=&cursor=&limit=` | staff, super_admin | typed page from one source; per-type cursors (no merged-cursor machinery) |
| `POST /admin/moderation/{type}/{item_id}/approve` | staff, super_admin | body `{note?}`; delegate to source → commit → best-effort publish |
| `POST /admin/moderation/{type}/{item_id}/reject` | staff, super_admin | same |
| `GET /admin/ops/flags` | super_admin | list `feature_flags` rows |
| `PUT /admin/ops/flags/{key}` | super_admin | body `{enabled}`; toggles **existing** rows only (404 unknown key — no create); `audit(action="ops.flag_changed", meta={key, enabled})` in-tx; `reset_flag_cache()` after commit |

Kill switches are these same flag toggles (`ads_enabled`,
`billing_enabled`); coins rule switches already exist in the D13 coins
admin — the console links to them, no new backend.

## 3. Serving + tracking — `modules/ads`

### 3.1 Routes

| route | auth | flag | behaviour |
|---|---|---|---|
| `GET /ads/serve?slot=&pincode=` | `public=True` (+ public_routes.txt), rate-limited | 404-while-dark | eligibility → freq-cap → weighted pick → creative payload |
| `POST /ads/impressions` | public, rate-limited | 404-while-dark | beacon: dedupe → insert partitioned row |
| `POST /ads/clicks` | public, rate-limited | 404-while-dark | same |
| `/admin/ads/*` (campaigns, creatives, placements CRUD; `GET /admin/ads/stats`) | staff, super_admin | not flag-gated (admin can stage while dark) | see §3.4 |

Flag gating uses billing's `_require_flag` pattern: flag off → the
surface does not exist (404, never 403).

### 3.2 Eligibility + geo semantics

Given `(slot_key, pincode)`:

1. Resolve pincode → district → state via `shared.geo`
   (`district_for_pincode`); unknown pincode → only `{}`-targeted
   placements are eligible.
2. Eligible = placement.status active ∧ slot_key matches ∧ campaign
   status active ∧ `flight_start <= today <= flight_end` ∧ campaign has
   ≥ 1 approved creative ∧ geo match.
3. Geo match: `geo_target == {}` (everywhere) ∨ pincode ∈
   `geo_target.pincodes` ∨ `geo_target.district == district.lgd_code` ∨
   `geo_target.state == state.lgd_code`. Nothing else matches — a
   Coimbatore-district placement never serves for Chennai 600001.
4. Frequency cap: skip placements the viewer has already been served
   `AD_FREQ_CAP_PER_DAY` (default 3) times today — Redis
   `INCR freq:{viewer_hash}:{placement_id}` with TTL to end of UTC day.
5. Share-of-voice: weighted random choice over survivors by
   `placement.weight` (injectable RNG for deterministic tests).
6. Response: `{placement_id, creative_id, slot_key, label: "sponsored",
   creative: {title, body, media_urls, target_url}}` — copy resolved
   from an optional `locale` query param (`en|ta|hi`, default and
   fallback `en`), media keys resolved to URLs via the shared
   media/storage helper. No eligible placement → 204.

`label: "sponsored"` is part of the wire contract; the component renders
its own badge regardless (defense in depth on non-negotiable 1).

### 3.3 Viewer identity, dedupe, click fraud

- `viewer_hash = sha256(settings.secret_key + UTC_date + client_ip +
  user_agent)` — rotates daily, so no durable tracking identifier
  (privacy), while staying stable enough for same-day capping/dedupe.
- Beacon dedupe: Redis `SET NX EX 60` on
  `dedupe:{imp|clk}:{viewer_hash}:{placement_id}` — inside the window
  the beacon is accepted (200, no error signal to probes) but not
  inserted.
- Click fraud v1 (per threat model): dedupe now + append-only raw rows
  (viewer_hash, occurred_at) enabling later rate analysis. No scoring in
  v1.

### 3.4 Admin CRUD + stats

- `POST /admin/ads/campaigns` validates `advertiser_business_id` through
  the `shared.lookups` business resolver; CRUD for campaigns, creatives,
  placements with cursor-paginated lists (`shared.pagination.paginate`).
- Creatives are created `pending` — **even admin-created ones** go
  through the approval queue (uniform pipeline; the approver need not be
  the uploader).
- `target_url` validated on create (http/https, length) and re-checked
  at serve; `slot_key` validated against `SLOT_KEYS`; `geo_target`
  validated by Pydantic schema (unknown keys rejected).
- `GET /admin/ads/stats?placement_id=&date_from=&date_to=` → per-day
  `{date, impressions, clicks}` (GROUP BY day over the partitioned
  tables; range-bounded so it prunes partitions). Internal view only —
  D55 exposes advertiser-facing counts.

### 3.5 Worker

`modules/ads/worker.py` — billing-worker pattern: standalone poll loop
(`python -m modules.ads.worker`), enabled by `settings.ads_worker_enabled`
(env; worker not started → zero cost). The tick itself is NOT gated on
the `ads_enabled` DB flag: its only job in v1 is
`ensure_partitions(days_ahead=7)` via `DATABASE_ADMIN_URL`, and
partitions must exist before the flag ever flips (beacons 404 while dark
anyway). Any future serving-related tick work must check the flag.
Poll interval 6h.

## 4. Frontend

### 4.1 `@agri/ui` — `<SponsoredAd>` (the component contract)

- Renders the `★ Sponsored` badge **unconditionally** — not a prop, not
  conditional. Badge uses design-system sponsored tokens (no raw hex;
  `check:hex` gate applies).
- Props: creative payload + callbacks. Fires impression beacon on mount
  (once), click beacon on click; link opens with
  `rel="noopener nofollow sponsored"` `target="_blank"`.
- Copy rendered as plain text (React escaping; no
  `dangerouslySetInnerHTML`).
- Contract tests: badge present in every render; hostile copy
  (`<script>`, `<img onerror>`) renders inert; beacons fired once.

### 4.2 web-agri — one live slot

- BFF proxy `app/api/ads/[...path]/route.ts` with
  `ALLOWED_FIRST_SEGMENTS = {"serve", "impressions", "clicks"}` (D20
  billing-proxy precedent; no bearer needed — public endpoints, but the
  proxy keeps API_BASE_URL server-side and uniform).
- Directory browse page: one slot above results, fed by
  `/api/ads/serve?slot=directory_browse&pincode=<active location>`.
  Flag off (404) or 204 → renders nothing (no layout shift: slot
  collapses).

### 4.3 web-admin — Ops Console

- New `/ops` area, linked from the home page:
  - **Moderation** — ONE shared `components/moderation-queue.tsx`
    (extracted/evolved from claims-manager's `QueueSection<T>`): type
    tabs with pending counts (`/admin/moderation/summary`), typed item
    renderers (claim: evidence strip; review: stars + target chip;
    creative: media preview + copy + target_url shown as text),
    approve/reject with note via the unified endpoints, 409 →
    soft-drop item (reviews-manager precedent).
  - **Flags** — switch list from `/admin/ops/flags`, confirm Modal per
    toggle (kill-switch semantics), controls disabled unless
    super_admin; link to `/coins` for coins rule switches.
- `/claims` and `/reviews` pages **deleted**; routes redirect to `/ops`
  (D22 gate: "one moderation queue, no duplicates"). The forked
  `QueueSection` copies die here.
- **Ads admin** — `/ads` page: campaign list/create, creative
  create (media upload via existing shared presign path, or key entry),
  placement create with slot + geo pickers (state/district/pincodes),
  stats table per placement.
- web-admin's `/api/admin/[...path]` proxy already fronts `/admin/*`;
  the new `/admin/moderation|ops|ads` routes need no proxy changes.

## 5. Events & notifications

| event | stream | emitted | consumed |
|---|---|---|---|
| `creative.approved` / `creative.rejected` | `ads` | creative source decision | nobody in v1 (future advertiser notify/D55) |
| `review.approved` | `directory` | unchanged — now captured by the review source, published by ops router | coins worker + notify (existing) |
| claim/verification events | `directory` | unchanged, via claim source | search indexer etc. (existing) |

No new EVENT_ROUTES entries (no new notifications in v1 — deliberate; a
seeded template without EVENT_ROUTES is the known trap, so we add
neither).

Audit actions: existing strings preserved for claims/reviews;
new `ads.creative_approved|rejected`, `ops.flag_changed`,
`ads.campaign_created` etc. — metadata carries IDs/notes, never PII.

## 6. Tests (mapped to non-negotiables)

1. **Sponsored label** — `@agri/ui` contract test (badge in every
   render, hostile copy inert); backend test: serve response carries
   `label == "sponsored"`; web-agri slot test renders badge.
2. **Geo 641001** — with `tn_geo_sample`: Coimbatore-district placement
   serves for 641001, NOT for 600001; pincode-list, state-level, and
   `{}`-target cases; unknown-pincode case.
3. **Partition day boundary** — inserts at D 23:59:59Z and D+1 00:00:01Z
   land in distinct partitions (pg_catalog check); with only DEFAULT
   present the insert still succeeds; `ensure_partitions` idempotent
   (double run = no error, no dup).
4. **Unified queue** — summary counts all four sources; per-type list
   pages correctly; approve via unified route drives the real domain
   effect (claim → business owned + verification row; review → approved
   + aggregate recomputed + `review.approved` published; creative →
   approved + servable); reject paths; double-decide → 409; fake-source
   registration test (extensibility contract).

Threat-model & mechanics: beacon dedupe window; freq-cap exhaustion
(4th serve skips placement); share-of-voice distribution with seeded
RNG; `target_url` scheme rejection (`javascript:`, `data:`) at create
and serve; flag-off → 404 on all three public routes; append-only
trigger rejects UPDATE/DELETE as owner and app_rt; migration grant
assertions (app_rt: no UPDATE/DELETE on impressions/clicks); flags API:
non-super_admin 403, unknown key 404, audit row + cache reset verified;
storm suite (`@pytest.mark.slow`): concurrent beacon inserts, zero
loss/dup within dedupe semantics.

## 7. Out of scope (v1)

- Advertiser self-serve (D55): campaign creation UI for businesses,
  advertiser-facing stats, budgets with real money math.
- Click-fraud scoring/rate analysis (raw data retained for it).
- Meilisearch indexing of ads (serving is SQL-only at v1 volume).
- Catalog-product source registration (designed for, not wired).
- Partition retention/archival policy (revisit before volume).
