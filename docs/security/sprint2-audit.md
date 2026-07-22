# Sprint 2 adversarial + seam audit (D22, 2026-07-22)

Scope: adversarial and integration-seam audit of Sprint-2 work packages D15–D21
(migrations 0015–0022; new shared surfaces: media helper, coins events,
moderation queue, Business Console, search reindex, billing flag). No new
features. Per the D13 lesson, the audit weights integration seams heavily.

Severity legend: **Critical** / **High** must be fixed before the v0.3.0 tag
(non-negotiable). **Medium** / **Low** / **Info** are recorded and triaged;
deferrals carry a written reason (see Part B decisions at the end).

Method: six seam scopes (A1–A6) audited read-only from the committed tree by
independent fresh-context reviewers, then compiled here. Findings cite
`file:line` evidence and mark **Confirmed** (verified against actual code) vs
**Theoretical** (hypothesis needing follow-up).

---

## A1 — Migration chain integrity (committed tree)

**Result: CHAIN IS FULLY CLEAN.** No duplicate revisions, no filename/internal-revision
mismatches, single linear chain with exactly one head (`0022`) and one base
(`0001`), no gaps, no branches, no multiple heads, no stray/backup/orphaned
files, and committed tree == working tree. The exact D13 dup-revision defect
does **not** recur in the Sprint-2 (0015–0022) range or anywhere in the chain.

### Auditable chain table

| filename | internal `revision` | `down_revision` |
|---|---|---|
| 0001_schemas.py | `0001` | `None` (base) |
| 0002_slug_redirects.py | `0002` | `0001` |
| 0003_feature_flags.py | `0003` | `0002` |
| 0004_geo_v1.py | `0004` | `0003` |
| 0005_demo_all_mixins.py | `0005` | `0004` |
| 0006_pg_stat_statements.py | `0006` | `0005` |
| 0007_identity_v1.py | `0007` | `0006` |
| 0008_identity_seed_roles.py | `0008` | `0007` |
| 0009_oauth_v1.py | `0009` | `0008` |
| 0010_sessions_v1.py | `0010` | `0009` |
| 0011_profiles_rbac_v1.py | `0011` | `0010` |
| 0012_coins_v1.py | `0012` | `0011` |
| 0013_audit_v1.py | `0013` | `0012` |
| 0014_notify_v1.py | `0014` | `0013` |
| 0015_coins_harden_app_rt.py | `0015` | `0014` |
| 0016_directory_v1.py | `0016` | `0015` |
| 0017_claims_v1.py | `0017` | `0016` |
| 0018_catalog_v1.py | `0018` | `0017` |
| 0019_reviews_v1.py | `0019` | `0018` |
| 0020_leads_v1.py | `0020` | `0019` |
| 0021_billing_v1.py | `0021` | `0020` |
| 0022_ads_v1.py | `0022` | `0021` |

Reconstructed chain (head → base): `0022 → 0021 → … → 0015 → 0014 → … → 0001 → None`.
22 nodes, 22 files, unbroken.

- **[A1-1] Info — Filename ordinal matches internal `revision` for all 22 files.**
  Every file declares `revision: str = "00NN"` where `NN` equals its filename
  ordinal (e.g. `0015_coins_harden_app_rt.py:33 revision = "0015"`;
  `0022_ads_v1.py:35 revision = "0022"`). Zero mismatches. Confirmed.
- **[A1-2] Info — No duplicate `revision` values (D13 dup-revision class absent).**
  `grep -rhE '^revision: str = ' versions/*.py | sort | uniq -d` returned empty;
  `0001`–`0022` each appear exactly once. Confirmed.
- **[A1-3] Info — Single linear chain: one base, one head, no branches/gaps.**
  Exactly one `down_revision = None` (`0001_schemas.py:21`); no revision id is a
  `down_revision` more than once (no branch point); `0022` is the sole head.
  `0015` ↓ `0014` confirmed (`0015_coins_harden_app_rt.py:34`). Confirmed.
- **[A1-4] Info — Committed tree == working tree.** `git status --porcelain` and
  `git diff HEAD` for the versions dir both empty; `git show HEAD:` spot-checks of
  0015 and 0022 IDENTICAL to disk. Confirmed.
- **[A1-5] Info — No orphaned/duplicate/backup migration files.** Exactly 22
  contiguous `.py` migrations plus `__pycache__/`; no `.py.bak`, no stray copies,
  no rogue revision node outside `versions/`. Confirmed.

---

## A4 — Shared component & console seams

**Result: ALL FOUR SEAMS CLEAN.** The frontend is five separate Next.js zones
(`web-agri`, `web-milk`, `web-organic`, `web-admin`, `web-id`), each with its own
`SiteHeader`; "single mount" is evaluated per-zone. Shared primitives live in
`@agri/ui` (`packages/ui`). Only nit is a cosmetic stale comment.

| Item | Verdict |
|---|---|
| Location switcher | Single mount confirmed — one `LiveLocationPill` per consumer zone; admin/id correctly have none |
| Coins pill | Single mount confirmed — one `CoinsBalancePill` per header; web-id/demo usages are page-content/showcase |
| Unified moderation queue | Single unified queue confirmed — one `ModerationQueue` in `/ops`; `/claims` & `/reviews` are redirect stubs; `/ads` is management, not moderation |
| Business Console mount | Single mount confirmed — one `business/layout.tsx` + registry; proxy allowlist honored |

- **[A4-1] Info — Location switcher single mount per zone.** `LiveLocationPill`
  (`packages/ui/src/components/live-location-pill.tsx:83`) rendered once per zone
  via the header `location` slot (`apps/web-*/app/header-location.tsx:21`,
  self-documented as "the ONE location switcher (D19)"). `web-admin` omits it by
  design; `web-id` has no `SiteHeader`. Only other usage is the `/demo` showcase.
  Confirmed.
- **[A4-2] Info — Coins pill single mount per zone.** One `CoinsBalancePill`
  (`packages/ui/src/components/coins-balance-pill.tsx:44`) in each header's right
  cluster; renders nothing pre-load (no double-pill/empty risk). `web-id/coins`
  page and `/demo` are page-content/showcase, not header dupes. Confirmed.
- **[A4-3] Info — Unified moderation queue confirmed.** `OpsManager`
  (`apps/web-admin/app/ops/ops-manager.tsx:195`) renders a single
  `ModerationQueue`; four tabs (`claim`, `verification`, `review`, `creative`)
  route through it via a `renderItem`/`mediaUrl` config switch. Legacy
  `/claims` & `/reviews` are `redirect("/ops")` stubs; `/ads` is
  campaign/creative *management* that never flips `moderation_status` (only `/ops`
  does). Confirmed. Nit: stale `reviews-manager.tsx` reference in a comment at
  `ops-manager.tsx:29-31` (component no longer exists).
- **[A4-4] Info — Business Console single mount + proxy allowlist honored.** One
  `business/layout.tsx:25` driven by `CONSOLE_MODULES`
  (`apps/web-agri/lib/console-modules.ts:21`, documented "THE mount contract —
  extend, not fork"); imported by that layout only. Billing module gated by
  `billing_enabled` probe (404 = dark). Proxy allowlist at
  `apps/web-agri/app/api/billing/[...path]/route.ts:21` restricts `path[0]` to
  `{subscription, subscriptions, invoices}`, rejects `webhook`/`admin/*` with 404
  before attaching the bearer, plus path-traversal guard. Confirmed.

---

## A2 — app_rt grant matrix

**Result: the three headline append-only tables — `ads.impressions`, `ads.clicks`,
`billing.payment_events` — are correctly locked for `app_rt` (no UPDATE, no
DELETE), as are `leads.contact_reveals`, `coins.ledger_entries`, `audit.entries`.**
All compose request/worker services connect as `app_rt`; only migrations and the
ads partition-DDL worker use the owner `app` role (legitimate: `app_rt` has no
CREATE). No confirmed exploitable UPDATE/DELETE on an append-only table. Two
defense-in-depth gaps (one MED, one LOW) + one informational.

Role model: `app_rt` (LOGIN NOSUPERUSER) created in `0013_audit_v1.py:83-97` is
the runtime role; `app` is the table owner, migrations/DDL only. `0013:98-107`
grants `app_rt` blanket `SELECT,INSERT,UPDATE,DELETE ON ALL TABLES` + `ALTER
DEFAULT PRIVILEGES … GRANT S,I,U,D` for the app schemas — this default-privilege
grant is the root cause of A2-1. Append-only tables are then individually
narrowed by explicit `REVOKE UPDATE,DELETE FROM app_rt`.

Append-only verification (explicit):
- `ads.impressions`/`ads.clicks` (parents): U/D REVOKED (`0022_ads_v1.py:171-173`)
  **and** BEFORE UPDATE/DELETE trigger `forbid_tracking_mutation()`
  (`0022:154-166`) blocks all roles. Locked.
- `billing.payment_events`: U/D REVOKED (`0021_billing_v1.py:333`). Locked at
  grant level (no trigger backstop).
- `leads.contact_reveals`: U/D REVOKED (`0020_leads_v1.py:135`). Locked at grant level.
- `coins.ledger_entries`: U/D REVOKED (`0015:40`) + immutability trigger from 0012.
- `audit.entries`: SELECT,INSERT only (`0013:110`).

Runtime role per service: dev `api`→`app_rt` (`docker-compose.dev.yml:10`), coins
`worker`→`app_rt` (`:43`), `search-worker`→`app_rt` (`:61`); `settings.py:30`
runtime default = `app_rt`, `:31` admin = `app` (migrations/tests only);
`modules/ads/worker.py:27` uses admin for partition DDL only (legitimate);
staging `api` gets no owner creds. All request/worker paths use `app_rt`.

- **[A2-1] MEDIUM — app_rt retains UPDATE/DELETE on ads impression/click
  partitions (grant-level defense-in-depth gap).** The parent REVOKE
  (`0022_ads_v1.py:171-173`) doesn't cover partitions; 0013's schema-wide `ALTER
  DEFAULT PRIVILEGES` re-grants all four DML to `app_rt` on every partition
  (`_default`, pre-created, and future ones from `modules/ads/maintenance.py:36-42`).
  Grant gap **Confirmed**; exploit **Theoretical** — the BEFORE UPDATE/DELETE
  trigger propagates to all partitions and still hard-blocks the mutation.
  *Fix:* `REVOKE UPDATE, DELETE ON ads.<partition> FROM app_rt` after each
  partition create (in 0022 and in `ensure_partitions`), or narrow 0013's `ads`
  default-privileges to `SELECT, INSERT`.
- **[A2-2] LOW — privileged owner DSN (`app:app`) injected into the dev `api`
  container that never uses it** (`docker-compose.dev.yml:11`
  `DATABASE_ADMIN_URL`). The web process only connects as `app_rt`; admin URL is
  consumed only by `alembic/env.py`, `modules/ads/worker.py`,
  `scripts/migrate_check.py`. Confirmed present+unused; owner creds bypass every
  grant restriction (`DISABLE TRIGGER`), so any env disclosure on the
  internet-facing process = full mutate/delete on append-only tables. Dev-only
  blast radius (staging doesn't carry it). *Fix:* remove from `api`; run
  migrations via a one-shot step.
- **[A2-3] LOW/Info — `billing.payment_events` (and `leads.contact_reveals`)
  immutability is grant-only, no trigger backstop** (`0021:331-333`), unlike
  ledger/ads which also have triggers. A single future accidental `GRANT
  UPDATE … ` or `GRANT ON ALL TABLES IN SCHEMA billing` silently re-opens it with
  no second line of defense. Deliberate documented design ("append-only BY
  GRANT"). *Fix (optional):* add BEFORE UPDATE/DELETE trigger for parity, and/or a
  CI assertion that these tables never hold U/D for `app_rt`.
- **Hygiene note:** directory migrations use schema-wide `GRANT … ON ALL TABLES`
  (`0016:172`, `0017:182`) — benign today (all directory tables mutable) but a
  latent trap if a future append-only directory table is added; leads/billing/ads
  correctly switched to per-table grants. Sequences grant is USAGE,SELECT only
  (appropriate). No explicit `REVOKE … FROM PUBLIC` observed in Sprint-2
  migrations (traces to 0001 bootstrap, out of A2 scope — worth confirming).

---

## A5 — Shared media helper

**Result: D16 (directory/claims) and D17 (catalog/products) share the SINGLE
`shared.media.reencode_image` path with NO fork.** No presigned direct-to-bucket
path exists anywhere (all bytes flow server-side through `reencode_image` →
`shared.storage`), so "no presign fork" is trivially satisfied. A CI lint gate
(`test_no_media_helper_fork`) mechanically forbids PIL use outside
`shared/media.py`. The pre-decode pixel guard is enforced on every path that
decodes untrusted image bytes. No Critical/High.

Pipeline (`shared/media.py`, single `reencode_image(bytes)→(bytes,"image/jpeg")`):
empty reject (`:33`), 5 MiB size cap on raw bytes before decode (`:35`), format
allowlist JPEG/PNG/WEBP via header-only `Image.open` (`:37-43`), **pre-decode
40 MP pixel guard** `width*height > MAX_IMAGE_PIXELS` checked **before**
`img.load()` (`:49-50`, closes the 40–80 MP window Pillow's own
`DecompressionBombError` misses), Pillow bomb backstop (`:52-54`), EXIF/GPS/XMP/ICC
stripped by construction via `convert("RGB").save(JPEG)` (`:57-59`).

Callers (all funnel through the one helper): product images
`modules/directory/catalog_router.py:235-238`; claim evidence + verification docs
`modules/directory/claims_router.py:69-72,143-150` (both via `_store_evidence`).
Reviews are text-only (no media). Ads accept `media_keys` strings (no byte
ingestion).

- **[A5-1] Info/PASS — D16 & D17 share one un-forked path.** Both call
  `media.reencode_image` after `file.read(MAX_IMAGE_BYTES+1)`; grep for
  `Image.open|from PIL|reencode|exif|presign` returns zero production hits outside
  `shared/media.py`. Confirmed.
- **[A5-2] Info/PASS — pixel guard on every byte-ingesting path.** Exactly three
  endpoints decode untrusted bytes; all three go through `reencode_image`.
  Confirmed.
- **[A5-3] Info/PASS — CI lint gate forbids a future fork.**
  `tests/lint_checks.py:62-79` + `test_no_media_helper_fork` allowlist only
  `shared/media.py`. Confirmed. (Minor: regex misses aliased `import PIL.Image as
  x`; documented accepted tradeoff.)
- **[A5-4] LOW — ads `create_creative` accepts arbitrary `media_keys` strings with
  no key-provenance check** (`modules/ads/admin_router.py:130-157`,
  `schemas.py:65-73`). No byte ingestion (so not a media-pipeline fork), but a
  staff/super-admin can point a creative at *any* storage key (e.g. another
  tenant's `claims/` evidence) and `get_creative_media` (`:181`) streams it back
  as `image/jpeg` with no ownership check on the referenced key. Staff-only →
  LOW. Cross-referenced under A6b (ads authorization). *Fix:* validate
  `media_keys` against an `ads/` prefix and/or verify ads-owned provenance.
- **[A5-5] Info (out of scope, D06) — avatar upload uses a different path.**
  `modules/identity/profile_router.py:162-173` stores raw bytes via
  `storage.put_object` after magic-byte sniff — no `reencode_image`, so no
  EXIF-strip and no pixel guard. Intentional per D06 (decodes nothing → no bomb
  exposure), outside D15–D21 scope. Not a fork. *Recommendation (defer to D06
  owner):* route avatars through `reencode_image` for uniform EXIF-strip.

---

## A3 — Event-stream contract

**Bus mechanics** (`shared/events.py`): Redis Streams, one consumer group per
interested module (every group sees every event once). No XAUTOCLAIM/idle sweep;
`reap_poison()` only DLQs entries with `times_delivered >= 3`, which never
increments for an event read once and left unacked. **Positive result on the
contract-break class:** no consumer raises on an unexpected event type — search,
coins, and notify workers all guard with a membership/route lookup and no-op on
anything unrecognized; the create/approve paths for business, product, review and
claim each fire the exact event(s) the indexer/coins handler expect, with the
required payload fields present. The genuine risks are durability + deploy wiring.

Producers (Sprint-2): `business.created` (directory/router.py:172),
`business.updated` (many sites incl. moderation_sources.py), `business.claimed`
(admin_router.py:191, moderation_sources.py:106), `product.created`
(catalog_router.py:169, snapshot null — new products pending), `product.updated`,
`directory.claim_rejected`, `directory.verification_approved/rejected`,
`review.approved` (reviews_admin_router.py:117, moderation_sources.py:400),
`lead.created`/`lead.responded` (leads_router.py:132/206), `billing.*`
(billing/service.py:117-299; `subscription_renewed` deliberately unrouted),
`coins.balance_drift` (coins/integrity.py:62, payload has no `user_id`).
Consumers: search worker (directory stream → business/product create/update),
coins worker (identity+directory → user.registered, profile.completed,
session_resumed, business.claimed, review.approved), notify worker (per
`EVENT_ROUTES`).

- **[A3-1] HIGH — best-effort publish silently drops events → permanent missing
  coins award / stale index (no transactional outbox).** Every producer commits
  the DB txn first, then publishes outside the txn in a `try/except Exception`
  that only logs (`_publish_best_effort`/`publish_pending`;
  directory/router.py:66-72, admin_router.py:89-96, catalog_router.py:50-56,
  leads_router.py:54-61, billing/service.py:66-77). No outbox, no retry. If Redis
  blips during `approve_claim`'s publish window, the committed claim gives the
  business an owner but `business.claimed` is dropped → claimant **never** gets
  the `business_claim` coins award, and dropped `business.updated` leaves the
  business `verified:false` in Meili until manual reindex. Confirmed (best-effort
  by construction; divergence unrecoverable without operator action). *Fix:*
  transactional outbox, or at minimum a metric/alert on publish failure.
- **[A3-2] HIGH — search & coins workers are standalone processes not started by
  the app lifespan; only the notify worker is wired into `main.py:156-172`.**
  `search/worker.py` and `coins/worker.py` are `python -m` entrypoints. If a
  deployment doesn't separately launch both, business/product events accumulate
  unconsumed (stale/empty Meili) and coins events starve (zero awards) — invisible
  to the API. Confirmed as a wiring dependency. *(Auditor note to verify: dev
  docker-compose does run `worker` and `search-worker` as separate services;
  severity hinges on whether every deploy manifest — incl. staging — does the
  same + has lag alerting.)*
- **[A3-3] MEDIUM — consumer-side exception loses the event with no redelivery.**
  On `apply_event`/`handle_event` raising, the event is left unacked and logged;
  with no idle-claim sweep it is neither retried nor DLQ'd
  (search/worker.py:39-56, coins/worker.py:144-158, notify/worker.py:34-49). A
  transient Meili timeout permanently drops that document update until an operator
  runs `scripts/reindex_search.py`. Confirmed (documented limitation). *Fix:*
  XAUTOCLAIM idle-based redelivery in `EventConsumer` (the "pre-VPS fast-follow").
- **[A3-4] LOW — `coins.balance_drift` published with no consumer and a payload
  (`{count, user_ids}`) missing `user_id`** (coins/integrity.py:62). Dead event
  today (alerting relies on log+metric); latent KeyError trap if a route is later
  added. *Fix:* drop the publish or give it a proper admin route + valid recipient.
- **[A3-5] LOW/Theoretical — verification events assume `owner_user_id` non-null.**
  Effectively unreachable (verification requires an owned business, no unclaim
  path). No action required; optional guard.
- **[A3-6] INFO — seeded notify templates must have an `EVENT_ROUTES` entry (D18
  trap).** Not exhaustively diffed this pass. *Fix:* CI assertion that every
  `EVENT_ROUTES` `template_key` is seeded.
- **[A3-7] INFO — dual producers (legacy admin routes + `/ops` moderation_sources)
  build the same event payloads independently** — benign today (only one surface
  decides a given item; consumers idempotent), maintenance hazard. *Fix:* factor
  payload builders into one shared helper.

---

## A6a — Attack surface: leads, reviews, directory, claims

(`modules/leads` and `modules/reviews` are empty stubs; the code lives in
`modules/directory/`.) **Headline: the contact-reveal cap holds under scripted
concurrent scrape** (atomic Redis `INCR`, no TOCTOU, fails closed to 503), and
**no contact PII leaks outside the reveal path** (public detail/`covers`/search
snapshot all omit phone/whatsapp/email). No Critical/High.

- **[A6a-1] Info/PASS — contact-reveal cap atomic, per-user, fail-closed.**
  `claim_reveal_slot` does `count = int(redis.incr(key)); if count > cap: raise`
  (`reveal.py:28-39`), key `reveal:{user_id}:{YYYYMMDD}`, cap 10
  (`settings.py:93`); `RedisError → 503`. Endpoint order: resolve → verify active
  → cap → log → commit (`router.py:376-404`). Sole choke point; no pagination path
  returns contact data. Confirmed under concurrency. *Minor hardening:* per-account
  only (K accounts → 10·K/day; add IP/device throttle if abused); make
  `INCR`+`EXPIRE` atomic (Lua/`SET NX EX`) so a crash between them can't pin a user
  at cap (availability nit).
- **[A6a-2] Info/PASS — no contact-PII leak outside reveal.** `_public_branch_out`
  omits phone/whatsapp (`router.py:127-140`); search snapshot forbids
  phone/whatsapp/email/owner_user_id (`search_sync.py:14-15`); `CoversItemOut` has
  no contact fields. Confirmed.
- **[A6a-3] LOW — reviews: no self-review / own-business review prevention.**
  `create_review` (`reviews_service.py:52-78`) doesn't check `author !=
  business.owner`. Limited by one-per-target unique constraint + pending-by-default
  (needs staff approval to be visible/awarded). *Fix:* reject reviews where author
  owns the target business/product.
- **[A6a-4] LOW — reviews "5/week" is a coin-award cap, not a submission cap.**
  A scripted user can submit one pending review against thousands of distinct
  targets, flooding the moderation queue (public aggregates unaffected — pending
  excluded). *Fix:* per-user submission rate limit; confirm SecureRouter default
  limit applies to `POST /reviews`.
- **[A6a-5] Info/PASS — directory/leads/claims IDOR: authorization is
  ownership-based, not ID-guess-based.** Every private read/write funnels through
  an owner-scoped query; non-owner and missing row both yield 404. No IDOR found.
  `POST /leads/inquiries` is intentionally `public=True` (guest lead), validated,
  one inquiry → one inbox (no fan-out). Confirmed.
- **[A6a-6] Info/PASS — claim races cannot double-award or double-own.** Partial
  unique index + savepoint on submit; `FOR UPDATE` + capture-before-commit on
  decision; coins idempotency key `claim:{business_id}`; only `owner_user_id IS
  NULL` businesses claimable. Confirmed race-safe.
- **[A6a-7] LOW — claim-farming: no per-user cap on pending claims/verifications.**
  One actor can open pending claims against arbitrarily many claimable businesses
  (cost: 1–5 evidence images each). Bounded by mandatory admin approval →
  queue-flooding, not automated takeover. *Fix:* per-user cap/rate-limit on
  concurrent pending claims.

---

## A6b — Attack surface: billing, ads, uploads

**Direct answers:** webhook replay yields one effect on *amounts* only by
downstream idempotency luck, **not** by the dedupe key (which is an unsigned
header → A6b-1); **flag-off = zero live billing surface today** (every handler
fails closed to 404, worker + client re-check); **every served ad is labeled
"Sponsored"** (`label: Literal["sponsored"]`, type-enforced,
`ServedAdOut`/schemas.py:151, single serve path router.py:78); **geo-mismatch
fails closed for honest input** (`geo_matches`, service.py:66-84) but pincode is
client-supplied (A6b-6). Uploads are well-hardened (no finding above Low).

- **[A6b-1] HIGH — webhook idempotency key is an unsigned, attacker-mutable
  header.** HMAC is over the raw body only
  (`router.py:68 hmac.new(secret, body, sha256)`); the dedupe key is a *separate*
  header `event_id = request.headers.get("x-razorpay-event-id")` (`:73`), not part
  of the signed payload. A captured validly-signed body re-POSTed with a **new**
  event-id passes signature check and the dedupe sees a new id → reprocessed.
  Content idempotency prevents double-crediting amounts, but
  `apply_subscription_charged` (`service.py:79-113`) sets `status="active"` and
  resets dunning **unconditionally** → replaying an old `subscription.charged`
  while a sub is `past_due` flips it back to `active`, zeroes
  `dunning_attempt`/`next_retry_at` with no real payment, appends a second
  `payment_events` row, re-fires notify. Mechanism confirmed in code; exploit
  conditional on capturing one valid webhook + entitlement keyed on `status`.
  *Fix:* derive the dedupe key from a field **inside the signed body** (event
  id/content hash), and/or guard transitions against stale events (ignore a
  `charged` whose period is older than the stored `current_period_end`).
- **[A6b-2] MEDIUM — no webhook timestamp/tolerance window** (`router.py:62-99`).
  A validly-signed body is accepted indefinitely, making A6b-1's replay unbounded
  in time. *Fix:* signed-timestamp tolerance window + in-body dedupe.
- **[A6b-3] Info — flag gate is per-handler, not a router dependency**
  (`_require_flag` called first line in each handler; worker + client re-check).
  Zero-surface holds today; risk is future-drift (a new handler forgetting the
  call). *Fix:* apply the flag as a router-level dependency (matches PRE-FLAG-FLIP
  intent).
- **[A6b-4] MEDIUM — ad beacons accept forged `creative_id`/`slot_key`
  attribution.** `_track` (`ads/router.py:88-123`) validates only that
  `placement_id` exists; client-supplied `creative_id`/`slot_key` are written
  verbatim. Beacons are `public=True`. Pollutes per-creative attribution (aggregate
  `placement_stats` counts by placement only, so bounded). *Fix:* validate
  `(placement_id, creative_id, slot_key)` consistency or derive server-side.
- **[A6b-5] MEDIUM — click/impression inflation via client-controlled User-Agent
  in the viewer hash.** Dedupe/freq-cap key on `viewer =
  sha256(secret:day:ip:user_agent)` (`service.py:62`); UA is attacker-controlled,
  so one IP mints unlimited viewers by varying UA, defeating the 60s dedupe + daily
  freq cap. Backstop is only the SecureRouter per-IP rate limit (60/window). No
  `X-Forwarded-For` trust (good). *Fix:* drop UA from dedupe identity; stricter
  per-IP beacon budget; treat click counts as advisory.
- **[A6b-6] LOW — geo targeting trusts a client-supplied pincode** (`serve`
  `public=True`, pincode query param; `ads/router.py:41-71`). Fail-closed for
  honest input, but a client can assert any pincode and receive that geo's ads
  (advertiser budget waste, not data exposure). *Fix:* document as client-asserted;
  optionally cross-check server-derived GeoIP band.
- **[A6b-7] Info(positive)/Low sub-item — uploads well-hardened; ads `media_keys`
  unvalidated.** No presigned direct-to-bucket upload; keys server-generated +
  namespaced (`avatars/{uuid7}`, `{PRODUCT_MEDIA_PREFIX}{uuid7}.jpg`); size cap +
  content allowlist-by-content + pre-decode pixel guard; upload endpoints private +
  IDOR-gated. Sub-item (LOW, = A5-4): ads `CreativeIn.media_keys` are arbitrary
  staff-supplied strings bypassing `reencode_image`; `get_creative_media` serves
  any key as `image/jpeg` (staff/super-admin only). *Fix:* route ads creative media
  through the same `reencode_image` + server-generated-key flow.

---

## Severity roll-up

Final severities (after verifying each High candidate against the committed code):

| Severity | Count | IDs |
|---|---|---|
| Critical | 0 | — |
| High | 2 — **both FIXED** | A6b-1 ✅fixed, A3-2 ✅fixed |
| Medium | 6 — all deferred w/ reason | A2-1, A3-1 (reclassified from High), A3-3, A6b-2, A6b-4, A6b-5 |
| Low | 9 — deferred/recorded | A2-2, A2-3, A5-4, A6a-1(nit), A6a-3, A6a-4, A6a-7, A6b-6, A6b-7(sub) |
| Info/PASS | many | A1-*, A4-*, A5-1/2/3/5, A6a-2/5/6, A3-4/5/6/7, A6b-3 |

**Zero Critical/High open at tag** (the D22 non-negotiable): both Highs are fixed
and verified; the third High candidate (A3-1) is reclassified to Medium with
written reasoning below and deferred.

---

## Part B — fix vs. defer decisions

### Fixed (both confirmed Highs)

- **[A6b-1] HIGH → FIXED.** Webhook replay dedupe key changed from the unsigned,
  attacker-mutable `x-razorpay-event-id` header to a SHA-256 hash of the
  HMAC-signed request body (`modules/billing/router.py:82-91`). The body is what
  Razorpay signs, so its hash is a tamper-proof idempotency key; Razorpay's own
  retries resend the identical body (same hash), preserving legitimate one-effect
  semantics. Verified test-first (red→green): new regression
  `tests/test_billing_webhook.py::test_replay_with_forged_event_id_cannot_reactivate`
  posts a valid charge, forces the sub to `past_due`, then replays the same signed
  body with a **forged** event-id header and asserts it stays `duplicate` /
  `past_due` (no reactivation, dunning not reset). Failed on the old header-keyed
  code, passes now; full `test_billing_webhook.py` green (9/9). Two dependent
  tests updated to key on the body hash.
- **[A3-2] HIGH → FIXED.** Added the coins `worker` and `search-worker` services
  to `docker-compose.staging.yml` (config only — no deployment, consistent with the
  staging-deferred owner policy). Dev compose already ran both; the staging/prod
  manifest omitted them, so the notify worker (in-process) ran but coins/search
  did not → zero awards + permanently stale Meili index behind a healthy-looking
  api. The two workers are standalone `python -m` processes on the same api image,
  connecting as `app_rt` via `secrets/staging.env`, mirroring dev. Manifest
  validated (both services parse, correct commands). *Deferred sub-item:*
  consumer-group lag alerting (XINFO GROUPS) so a not-running worker pages instead
  of silently starving — a VPS/observability fast-follow (staging obs is
  owner-driven/deferred).

### Deferred with reason

- **[A3-1] HIGH → reclassified MEDIUM, deferred.** *Reclassification rationale
  (transparent):* the auditor rated the best-effort-after-commit publish HIGH for
  "permanent missing award / stale index." I assess it **Medium** because: (a) it
  is a *deliberate, documented* design — `publish_pending`'s docstring
  (`service.py:66-68`) states best-effort-after-commit is chosen specifically so a
  Redis blip can never roll back a money transition and no event can exist for a
  rolled-back one; (b) it is **pre-existing since D16**, not introduced this
  sprint, and was already carried forward as a fast-follow in Gate 2; (c) it
  triggers only if Redis is unavailable during the narrow post-commit publish
  window; (d) every outcome is **operator-recoverable** — stale index via
  `scripts/reindex_search.py`, missing coins via balance-drift detection + manual
  adjust; (e) drops are already emitted as structured `*.publish_failed` /
  `event_publish_failed` warnings, so they are observable in logs today. *Why
  deferred, not fixed now:* the proper fix is a transactional outbox — a new
  architectural feature spanning ~9 producer sites across the money and directory
  paths; even the lighter mitigation (a uniform `EVENT_PUBLISH_FAILED` metric via a
  shared best-effort helper) requires touching all of those sites. Performing a
  broad refactor of the money path immediately before a v0.3.0 tag violates the
  D22 "no new features / boring, reversible, measured" constraints and adds
  regression risk. **Fast-follow:** transactional outbox + publish-failure metric,
  bundled with A3-3.
- **[A3-3] MEDIUM → deferred.** Consumer-side exception loses the event (no
  XAUTOCLAIM idle-claim redelivery); a once-failed apply is neither retried nor
  DLQ'd. Same durability family as A3-1, same recovery paths, documented as the
  "pre-VPS fast-follow" in all three workers. Fix (XAUTOCLAIM in `EventConsumer`)
  bundled with the A3-1 outbox work. Not exploitable; requires a transient
  consumer error.
- **[A2-1] MEDIUM → deferred.** `app_rt` keeps UPDATE/DELETE on ads
  impression/click *partitions* at the grant level (0013 default-privileges
  re-grant), but the `forbid_tracking_mutation()` BEFORE trigger propagates to
  every partition and **hard-blocks the mutation for all roles** — so the immutable
  guarantee holds; only the defense-in-depth grant layer is missing. Deferred as a
  hygiene fast-follow (`REVOKE UPDATE, DELETE` per partition in `0022` +
  `ensure_partitions`, or narrow 0013's `ads` default-privileges). No exploitable
  path today.
- **[A6b-2] MEDIUM → deferred.** No webhook timestamp/tolerance window. With A6b-1
  fixed, the replay vector (identical body) is already closed by content-hash
  dedupe, so a timestamp window is now purely additional defense-in-depth; also,
  billing is flag-OFF (no live surface). Deferred to the PRE-FLAG-FLIP checklist
  (add a signed-timestamp tolerance once relied upon).
- **[A6b-4] MEDIUM → deferred.** Ad beacons accept forged `creative_id`/`slot_key`
  (only `placement_id` is validated). Impact bounded — `placement_stats` aggregates
  by `placement_id` only, so headline counts are unaffected; only per-creative
  attribution is pollutable. Deferred: validate `(placement_id, creative_id,
  slot_key)` consistency or derive server-side, alongside A6b-5.
- **[A6b-5] MEDIUM → deferred.** Click/impression inflation by varying the
  client-controlled User-Agent in the viewer hash (defeats 60s dedupe + daily freq
  cap). Backstopped by the SecureRouter per-IP fixed-window limit (60/window) and
  no `X-Forwarded-For` trust, so magnitude is bounded; click counts are advisory.
  Deferred: drop UA from the dedupe identity + stricter per-IP beacon budget.
- **Lows/Info → recorded, deferred.** A2-2 (dev-only owner DSN in `api` container —
  remove from dev compose), A2-3 (payment_events/contact_reveals grant-only
  immutability — optional trigger for parity + CI assertion), A5-4/A6b-7 (ads
  `media_keys` unvalidated staff strings — route via `reencode_image` +
  server-generated keys), A6a-1 nit (make reveal `INCR`+`EXPIRE` atomic), A6a-3
  (reject self-reviews), A6a-4 (per-user review submission rate limit), A6a-7
  (per-user pending-claim cap), A6b-6 (document geo pincode as client-asserted).
  None are Critical/High; all bounded by existing controls (moderation gating,
  ownership scoping, rate limits, staff-only access). Triaged for the D23+ backlog.

<!-- END PART B -->
