# D26 — Vendor Dashboard: Design

Date: 2026-07-24 · Branch: `feat/d26-vendor-dashboard` · Sprint spec: `docs/Sprint/sprint3_D23-D32.md` (SPEC D26)

## Goal

One place where a vendor manages everything: listing, coverage pincodes, products,
delivery windows, a lead inbox (needs + contact leads) with response-time stats, a
premium-tier selector, and analytics-lite (views / reveals / leads by pincode). All
mounted into the D20 Business Console shell in web-agri — extend, never fork.

## Owner decisions (locked in brainstorming)

1. **Pre-billing tier selection is intent only.** Selecting Premium while
   `billing_enabled` is off records intent (`premium_requested_at`) and shows an
   "activates at launch" state. `Business.subscription_tier` stays `free` — it is
   never client-writable (threat model: fake premium via tier tampering). The sort
   machinery is proven via tests and a role-gated admin set-tier route.
2. **Premium sort = premium first, then distance.** `covers()` orders by
   `(tier_rank, distance_m, id)` with premium=0, free=1. D23 milk results and D24
   lists inherit the boost because they ride `covers()`.
3. **Profile views get a new append-only log + public beacon.** No tracking exists
   today; analytics-lite ships complete (views + reveals + leads by pincode).

## Approach

Thin extensions inside `modules/directory` (approach A). No new module, no event
consumers, no rollup tables: analytics aggregates `leads.inquiries`,
`leads.contact_reveals`, and the new `directory.profile_views` with direct SQL at
request time. Event-driven rollups (approach B) are right at scale but are YAGNI for
launch-sized traffic; revisit if analytics queries ever show up in slow-query logs.

Rationale for placement: import-linter independence means only `modules/directory`
can IDOR-check `directory.businesses` ownership (same reasoning as D17 catalog and
D18 leads-in-directory).

## Backend

### 1. Premium tier

- Migration: `businesses.premium_requested_at TIMESTAMPTZ NULL`.
- `PUT /directory/businesses/{business_id}/tier-selection` — owner-scoped
  (`get_owned_business`), body `{"tier": "free" | "premium"}`. `premium` sets
  `premium_requested_at=now()`; `free` clears it. Response includes current
  `subscription_tier` + `premium_requested_at` so the UI can render the
  "activates at launch" vs "active" state. Never touches `subscription_tier`.
- `POST /admin/directory/businesses/{business_id}/tier` — role-gated
  (`require_role`, directory-admin pattern), body `{"tier": "free" | "premium"}`,
  writes `subscription_tier`, audit-logged. This is how ops activates premium at
  launch and how tests/seed exercise premium sort.
- PATCH `update_business` continues to reject `subscription_tier` (existing
  one-way-door list) — regression test added.
- **Billing → tier auto-sync is explicitly out of scope.** Billing tiers are
  `growth/pro`, never write to directory, and the bridge belongs on the
  PRE-FLAG-FLIP checklist (PR #29 notes). D26 adds the checklist line: "map active
  subscription → subscription_tier=premium (and cancel → free) before flipping
  billing_enabled".

### 2. covers() premium sort

- SQL: select `CASE WHEN b.subscription_tier = 'premium' THEN 0 ELSE 1 END AS
  tier_rank`; `ORDER BY tier_rank, distance_m, id`; keyset predicate and cursor
  widen to the triple `(tier_rank, distance_m, id)`. Old two-field cursors are
  invalid → treated as `invalid_cursor` (existing error path); acceptable because
  cursors are short-lived page tokens, not stored.
- `CoversItemOut` already exposes `subscription_tier` — frontends need no wire
  change. D23 `milk/home` blend and D24 map/list consume `covers()` unchanged.

### 3. Profile views + analytics

- New table `directory.profile_views` (append-only by convention, ads
  `_TrackingColumns` precedent, no partitioning at this scale):
  `id (uuid7 pk), business_id (uuid, indexed), pincode (char(6) NULL),
  viewer_hash (text), occurred_at (timestamptz, indexed with business_id)`.
- `POST /directory/businesses/{slug}/view` — **public** (added to
  `public_routes.txt`), SecureRouter rate-limited, body `{"pincode": "641001"?}`
  (6-digit validated, optional). `viewer_hash = sha256(salt + ip + ua)` (ads
  pattern). Dedupe 1 view / viewer_hash / business / UTC-day via Redis
  SET-NX+EXPIRE, **fail-open** (Redis down → count the view; losing dedupe on a
  view counter is harmless, unlike caps). 404 for unknown/inactive slug. Returns
  204.
- `GET /directory/businesses/{business_id}/analytics?days=30` — owner-scoped.
  `days` ∈ {7, 30, 90}, default 30. Returns:
  - `views`: total + `by_pincode` (top 20, count desc) from `profile_views`.
  - `reveals`: total + by_pincode from `leads.inquiries` where
    `payload->>'source' = 'contact_reveal'`.
  - `leads`: total + by_pincode from `leads.inquiries` excluding
    reveal-attribution rows (contact leads + need children both count).
  - `response`: `total`, `responded`, `avg_response_seconds` — reuses the D18
    `_STATS_SQL` LATERAL shape (first response per inquiry), window-scoped to
    `days`.
  Single endpoint, a handful of aggregate queries; no new DTO conventions.

### 4. Listing extras

- Migration: `businesses.delivery_windows JSONB NULL` — list of
  `{"days": ["mon", ...], "open": "HH:MM", "close": "HH:MM"}` entries, max 7,
  validated server-side (known day keys, HH:MM format, open < close; overnight
  windows rejected in v1). Added to `MUTABLE_FIELDS` for PATCH; exposed on the
  public business detail DTO.
- Coverage editing reuses `PUT /directory/businesses/{id}/coverage` untouched
  (full-replace, 500-pincode cap). Products reuse `/catalog/*` owner CRUD
  untouched.

## Frontend (web-agri Business Console)

Mount contract (D20): each module = one route segment under `app/business/` + one
`CONSOLE_MODULES` entry; the layout is never edited.

- **`listings/` (replace stub):** business picker (inbox-client pattern via
  `GET /api/directory/businesses`), then: edit name/type/description/primary
  pincode (PATCH), delivery-windows editor, coverage editor (pincode chip list,
  6-digit validation, whole-list PUT), current verification/tier badges.
- **`products/` (replace stub):** vertical picker from `/catalog/verticals`;
  schema-driven form rendered from the active spec-schema's fields
  (string→input, number→number input, boolean→checkbox, enum→select; required/
  range/length from the field def; 422 `{code, field}` mapped to inline errors);
  product list (`/catalog/my/products`, keyset "load more"), create/edit/archive,
  image upload via existing multipart proxy pattern, moderation-status badges.
- **`inbox/` (extend):** type filter (contact vs milk_subscription — needs arrive
  as `milk_subscription` children with `delivery_time`/`note` in payload; render
  those fields), existing status filter kept; response-time nudge banner when
  `avg_response_seconds` exceeds a threshold (24h) — "Fast replies win more
  customers".
- **`analytics/` (new module entry):** business picker; range toggle 7/30/90;
  stat tiles (views / reveals / leads / avg response) + a by-pincode table.
  Built from `Card` + design tokens — no chart primitive exists in `@agri/ui`
  and none is added (analytics-*lite*).
- **`premium/` (new module entry, not billing-gated):** current plan card;
  billing flag ON → subscribe flow via existing `/api/billing` routes; flag OFF
  (404 probe) → tier cards with "activates at launch", selection persisted via
  tier-selection endpoint, selected state shown on revisit.
- **BFF:** new `/api/catalog/[...path]` proxy (billing allowlist template;
  allowlist: `verticals`, `my`, `products`, `businesses`). Tier-selection and
  analytics calls ride the existing `/api/directory` proxy, which already
  forwards owner-scoped directory paths (e.g. businesses list, coverage PUT);
  if that proxy turns out to have a first-segment allowlist, extend it — no new
  proxy either way.
- **Beacon:** fired from the public profile pages (web-milk
  `/directory/businesses/[slug]` and the web-agri directory page) — client-side
  `navigator.sendBeacon`/fetch to the view endpoint with the browsing pincode
  when known. Fire-and-forget; no UI.
- **i18n:** console convention is currently hardcoded English; D26 follows it
  (TA/HI for consoles arrives with D27's translation sweep).

## Security / threat model

- All vendor writes ride `get_owned_business` / owned-inquiry resolution;
  not-yours == 404 (existing IDOR contract). New routes (tier-selection,
  analytics) use the same helper — covered by IDOR tests.
- `subscription_tier` is server-set only: owner PATCH rejects it (existing),
  tier-selection cannot write it (by construction), admin route is role-gated.
- View beacon is public: rate-limited by SecureRouter defaults, deduped per
  viewer/day, stores only a salted hash (no PII, DPDP-consistent with ads
  tracking). Beacon accepts nothing but an optional pincode.
- No offset paging anywhere (keyset only; lint gate enforces).

## Testing

Backend (pytest):
1. **IDOR matrix (NN#1):** tier-selection, analytics, coverage PUT, product
   create/patch, inbox — other-owner's business/product/inquiry → 404.
2. **Premium sort (NN#2):** admin-set premium business ranks above nearer free
   ones in `covers()`; pagination across the tier boundary is stable and
   duplicate-free; tier-tamper attempts (PATCH subscription_tier, tier-selection
   with garbage) rejected.
3. **Response-time accuracy (NN#3):** seeded inquiries with known
   response deltas → exact `avg_response_seconds` assertion (windowed).
4. **Coverage → covers() (NN#4):** PUT adds pincode → business appears in
   `covers(pincode)`; PUT removes → disappears.
5. Views: beacon 204 + row written; same-viewer same-day dedupe; unknown slug
   404; analytics aggregation correctness by pincode (views/reveals/leads split).
6. delivery_windows validation matrix (bad day, bad time, open>=close, >7 rows).

Frontend/E2E (Playwright, reuse D25's login helpers + port hygiene):
- Console walk: login as vendor → edit listing → save coverage → create product
  via schema form → inbox respond → analytics page renders tiles.
- Premium page shows "activates at launch" with billing dark; selection persists.

CI: existing gates (backend, storm isolated, lighthouse floors untouched — console
pages are `robots: index false` and not in the lighthouse URL set).

## Out of scope (explicit)

- Billing→tier auto-sync (PRE-FLAG-FLIP checklist item, added there in this PR).
- Analytics rollup tables / event consumers / charts.
- Incremental coverage add/remove endpoints (whole-list PUT is enough).
- Overnight delivery windows; per-branch windows.
- Console i18n extraction (D27).
