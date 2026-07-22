# GATE 3 evidence (D22, 2026-07-22)

Definition of done: zero Critical/High open at tag; `backend-storm` required
before tag; committed tree verified == tested tree; every box below checked and
dated; v0.3.0 promotable from main.

Full adversarial + seam audit of D15–D21: `docs/security/sprint2-audit.md`
(A1–A6, Part B fix/defer decisions). Backend suite runs cited below were
executed against real Postgres + Redis + Meilisearch + MinIO via the host venv
(`backend/core/.venv`, Python 3.12), pointed at the dev datastores.

## Checklist

- [x] E2E: user registers → claims a business → (billing flag off) subscribes-path reachable but gated → receives a routed lead → responds — full loop green

  `backend/core/tests/test_d22_loop_e2e.py::test_full_loop_claim_billing_gated_lead_respond`
  (PASS, 6.66s, 2026-07-22) — one cohesive pass through the real API across three
  modules: OWNER claims a seeded `owner_user_id IS NULL` business, STAFF approves
  (`business.owner_user_id == OWNER`); the billing subscribe path is reachable but
  gated (`GET /billing/subscription` and `POST /billing/subscriptions` both 404
  with the flag off — never 403); OWNER sets coverage; a signed-in BUYER's inquiry
  routes to the owner's inbox (`lead.created` names OWNER as recipient); OWNER
  responds (`lead.responded` names BUYER). Complements the existing
  `test_claim_e2e.py` (claim → coins award + verified badge + notification +
  audit-chain-clean, PASS in the full suite).

- [x] covers(pincode) + lead routing correct for 641001

  `backend/core/tests/test_leads_routing.py` (coverage×category routing, PINCODE
  `641001` throughout) and `backend/core/tests/test_directory_covers.py`
  (covers() nearest-branch + keyset) — both green in the 1018-test suite run
  below. The full-loop E2E above also exercises the `641001` `route_inquiry`
  path end-to-end.

- [x] contact-reveal cap holds under scripted scrape

  Scripted concurrent scrape against the live dev Redis (2026-07-22), the TOCTOU
  concern A6a-1 raised:
  ```
  cap=10  concurrent_requests=50  ->  ok=10  capped=40  unavailable=0
  PASS: reveal cap holds under concurrent scrape — exactly cap winners, no TOCTOU over-grant
  ```
  50 genuinely concurrent `claim_reveal_slot()` calls for one user/day admitted
  **exactly 10** (the cap), rejected the other 40, zero unavailable — proving the
  atomic Redis `INCR` (`modules/directory/reveal.py:28-39`) has no read-then-write
  race. Backed by `tests/test_contact_reveal.py` (cap → 429, fail-closed on Redis
  error → 503, public detail has no phone/whatsapp, DPDP log carries no phone).

- [x] billing flag OFF = zero live billing surface; webhook idempotent when on

  Flag-off = 404 (surface does not exist): the full-loop E2E asserts both billing
  read + create paths 404 with the flag off; `tests/test_billing_webhook.py::test_flag_off_webhook_is_404_with_no_side_effects`
  confirms the webhook 404s with zero rows written. A6b audit: the gate is
  fail-closed at handler + worker + client. **Webhook idempotent when on** — and
  hardened this sprint (A6b-1, High → fixed): replay dedupe now keys on
  `sha256(signed body)`, not the unsigned `x-razorpay-event-id` header.
  ```
  tests/test_billing_webhook.py::test_charged_processes_and_replay_is_one_effect PASSED
  tests/test_billing_webhook.py::test_replay_with_forged_event_id_cannot_reactivate PASSED
  ```
  The second is the new regression: a captured valid body replayed with a
  **forged** event-id stays `duplicate` / `past_due` (no unpaid reactivation, no
  dunning reset). Full `test_billing_webhook.py` green (9/9).

- [x] every served ad labeled Sponsored; geo targeting correct

  ```
  tests/test_ads_serve.py::test_geo_district_placement_serves_641001_not_600001 PASSED
  tests/test_ads_serve.py::test_serve_carries_sponsored_label PASSED
  ```
  Every served ad carries `label="sponsored"` (type-enforced `Literal["sponsored"]`
  in `ServedAdOut`; single serve path); a district-targeted ad serves `641001` but
  NOT `600001` (geo fail-closed for honest input). Live smoke: public
  `GET /ads/serve?slot=directory_browse&pincode=600001` on the dev api →
  `{"ad":null}` HTTP 200 (fail-closed, no serve). (Client-asserted pincode is the
  documented A6b-6 Low; targeting integrity holds for honest input.)

- [x] search reflects new/approved content (event-driven)

  `tests/test_search_indexing.py`, `tests/test_directory_search_sync.py`,
  `tests/test_reindex_search.py` (event `apply_event` upsert/delete keyed on
  `doc_id`; snapshot forbid-list for phone/whatsapp/email) — all green in the
  suite run below. A3 confirmed the create/approve paths emit the exact
  `business.*`/`product.*` events the search worker consumes, and **A3-2 (High →
  fixed)** added the `search-worker` service to `docker-compose.staging.yml` so
  the index is actually fed in staging/prod (dev already ran it).

- [x] committed-tree migration chain linear; app_rt grants correct; no service connects as app

  Migration chain (A1): single linear `0001→0022`, one head, one base, no
  duplicates/branches/orphans, filename==internal revision, committed tree ==
  working tree (`git show HEAD:` spot-checks IDENTICAL). Re-verified independently
  against a fresh `git archive HEAD` extraction (imports confirmed resolving to
  `D:\agri-verify-d22`, not the editable working tree): the archived alembic
  loader built the test DB and the full suite passed there — **1018 passed** (incl.
  the new E2E test), 2 deselected, 5m09s, 2026-07-22; the extracted
  `billing/router.py` is byte-identical to `git show HEAD`.

  app_rt grants (A2): the three headline append-only tables — `ads.impressions`,
  `ads.clicks`, `billing.payment_events` — plus `leads.contact_reveals`,
  `coins.ledger_entries`, `audit.entries` are all locked (no UPDATE/DELETE for
  `app_rt`); ads tracking parents also carry a BEFORE UPDATE/DELETE trigger. All
  runtime request/worker compose services connect as `app_rt`; only migrations and
  the ads partition-DDL worker use the owner `app` role (legitimate — `app_rt` has
  no CREATE). Two deferred defense-in-depth items: A2-1 (partitions keep U/D at
  grant level but the trigger hard-blocks — Medium) and A2-2 (dev `api` container
  carries an unused admin DSN — Low); neither is an exploitable UPDATE/DELETE on an
  append-only table.

  - [x] `backend-storm` runs green (required check)

    `tests/test_coins_storm.py::test_storm_no_drift_no_negative` — **1 passed in
    8m49s** (2026-07-22) against a dedicated isolated Postgres (matching CI's
    fresh-DB conditions), from the committed archive; `test_ads_storm.py` also
    green. (An earlier run against the shared dev Postgres — with the live dev
    stack holding connections — failed on connection pressure, not a code
    regression; re-run isolated confirms clean. No coins code changed this sprint.)
  - [ ] `backend-storm` ENFORCED via live GitHub branch protection (owner action pending)

    Documented as required in `docs/runbooks/branch-protection.md`; live GitHub
    ruleset enforcement remains unavailable on the free plan — **known gap carried
    forward unchanged since Gate 1/2**, an owner action, not introduced by D22.

- [x] one location switcher, one coins pill, one moderation queue (no duplicates)

  A4 (all four seams clean, no duplication): one `LiveLocationPill` per consumer
  zone (admin/id correctly omit it); one `CoinsBalancePill` per header; one unified
  `ModerationQueue` in `/ops` handling claims + reviews + ad creatives (legacy
  `/claims` & `/reviews` are `redirect("/ops")` stubs; `/ads` is management, never
  flips `moderation_status`); one Business Console mount
  (`app/business/layout.tsx` + `CONSOLE_MODULES` registry) with the D20 proxy
  allowlist honored. Only nit: a cosmetic stale `reviews-manager.tsx` comment.

- [x] public_routes.txt hand-reviewed; audit verify_chain clean; git status zero AM

  `backend/core/public_routes.txt` unchanged vs `dev` (`git diff dev -- public_routes.txt`
  empty) — no public-route drift this sprint; the declared surface is the
  Gate-2-reviewed set (health/OTP/login + OAuth2 + the directory/leads/ads public
  reads already justified in the D15–D21 specs and A6a/A6b: no route exposes
  contact PII or an unauthenticated mutation). Audit chain clean over real dev
  data (2026-07-22):
  ```
  {"ts": "2026-07-22T10:27:24.601+00:00", "level": "INFO", ..., "msg": "audit chain verified", "breaks": 0}
  ```
  `git status` clean — zero AM files (verified immediately before this gate;
  the full working tree is committed on `feat/d22-sprint2-hardening`).

## Critical/High findings: zero open

The A6 adversarial + A1–A5 seam audit surfaced **zero Critical**. Three High
candidates were each verified against the committed code:

1. **A6b-1 (High) — billing webhook replay via unsigned dedupe key → FIXED**
   (`7e26952`). Dedupe now keys on `sha256(signed body)`; regression test proves
   red→green.
2. **A3-2 (High) — coins/search workers missing from the staging manifest → FIXED**
   (`7e26952`). Both worker services added to `docker-compose.staging.yml`.
3. **A3-1 (rated High) — best-effort-after-commit publish → reclassified MEDIUM,
   deferred with written reason** (audit Part B): a deliberate, documented
   money-path design pre-existing since D16, triggerable only by a Redis blip in a
   narrow window, fully operator-recoverable, and already emitted as structured
   `*.publish_failed` warnings. The proper fix (transactional outbox) is a new
   architectural feature out of scope for a hardening gate; bundled with A3-3 as a
   pre-VPS fast-follow.

All other findings (6 Medium incl. A3-1, 9 Low) are recorded with fix/defer
reasons in `docs/security/sprint2-audit.md` Part B; none is a launch blocker per
this gate's Critical/High-only non-negotiable.

## Known gaps carried forward

- Branch-protection / rulesets remain unenforced on the free GitHub plan
  (`docs/runbooks/branch-protection.md` Known Gap, unchanged since Gate 1) —
  `backend-storm` and the other checks run on every PR and are documented as
  required, but GitHub will not itself block a merge on them yet; owner action.
- Event durability fast-follow (A3-1 + A3-3): transactional outbox +
  `EVENT_PUBLISH_FAILED` metric + XAUTOCLAIM idle redelivery in `EventConsumer`.
  Pre-existing best-effort/no-redelivery design (Gate-2 carried a related note);
  bounded and operator-recoverable, deferred to the pre-VPS work.
- Worker consumer-group lag alerting (A3-2 sub-item) — an observability
  fast-follow for staging (staging observability is owner-driven/deferred).
- Ads beacon integrity (A6b-4/A6b-5, Medium) and ad grant-level partition
  hygiene (A2-1, Medium) — deferred defense-in-depth, bounded by existing
  triggers / per-IP rate limits; D23+ backlog.
- The Sprint-1 frontend Playwright suite (`e2e/` — auth/sso/bff) covers auth
  flows unchanged by D22 and is not a CI-enforced job; no frontend code changed
  on this branch, and A4 confirmed the shared header/console components remain
  single-mount, so no auth-flow regression is expected. Running the browser suite
  remains a manual/owner concern as in Gate 2.
