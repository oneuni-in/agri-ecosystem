# SPRINT 2 SPEC PACK — D15–D22: SHARED CORE FOR MILK.IN
# Aligned to v5 MASTER Block 3. One spec per fresh session · branch off dev → PR → dev → merge same day.
# Prereq: v0.2.0 tagged (Sprint 1 done). GATE 3 (D22): register→claim→subscribe(flagged)→receive-lead
#   E2E → promote dev→main → tag v0.3.0. Then Milk.in build (D23) begins.
#
# ▶ NEW THIS SPRINT — "INTEGRATION SURFACE" SECTION (added to every spec).
#   D13's integration write-up proved: specs are correct in isolation but bugs live in the SEAMS
#   (shared migrations, shared roles/grants, shared headers, shared event streams) that no single
#   spec's tests exercise. Each spec below now declares the shared surfaces it touches and how to
#   verify them against the COMMITTED tree, not the working tree.
#
# ▶ STANDING RULES CARRIED FROM D13/D14 (apply to every spec):
#   • Before every commit: `git status` shows ZERO files in AM state (staged-then-modified).
#   • After manual conflict resolution: verify the COMMITTED tree (git archive HEAD → scratch → run
#     alembic loader + suite) — a green LOCAL run is not proof of what's committed.
#   • Migration numbering: whoever merges to dev first wins lower numbers; a parallel branch renumbers
#     on integration (filename AND internal revision/down_revision strings — re-stage after editing).
#   • app_rt (restricted runtime role) gets only the grants a module needs; app (admin) does DDL/migrations.
#     New tables: confirm app_rt grants are correct; new immutable tables (like ledger/audit) get
#     trigger-level immutability, NOT just REVOKE.
#   • Shared header widgets integrate through @agri/auth-client's AuthCluster — extend the existing
#     integration point, never add a second widget beside it.
#   • Env reality: standalone Postgres on :45432 (host :55432 blocked by winnat); DATABASE_URL uses
#     app_rt, DATABASE_ADMIN_URL uses app. scripts/__init__.py must exist for mypy.

═══════════════════════════════════════════════════════════════
## SPEC D15 — DIRECTORY ENGINE + VENDOR↔PINCODE COVERAGE (~6h) · feat/d15-directory
═══════════════════════════════════════════════════════════════
CONTEXT: First shared engine — the workhorse ~60% of the ecosystem rides on. Module
backend/core/modules/directory. Businesses = any org/place (vendors, shops, labs, farms). Milk.in is
the first consumer; build vertical-agnostic. Uses D03 mixins + migration template; geo is TN-only (v5
D3 note) which is all Milk.in needs.

DO:
A. Tables (schema directory, via template): businesses (owner_user_id, name, slug [immutable], type
   ENUM, description i18n JSONB, status, verification_status ENUM unverified/pending/verified,
   subscription_tier ENUM free/premium, primary_pincode), branches (business_id, address, geo:
   state/district/pincode, lat/lng, phone, whatsapp, hours JSONB), business_categories (many-to-many
   to a categories table seeded with directory categories).
B. **Coverage model** (the Milk.in-critical piece): business_coverage (business_id, pincode) so a vendor
   serves many pincodes; query service covers(pincode) → businesses ordered by distance from pincode
   centroid; keyset-paginated. Index on (pincode) + geo.
C. Service layer: create/update business (owned_by owner), add/edit branches, set coverage, category
   assignment. All list endpoints cursor-paginated. SecureRouter; owner-scoped writes via owned_by().
D. Public read API: business detail by slug (SSR-ready), covers(pincode) search — both public, rate-limited.
E. Slug on immutable mixin + redirect table wired (rename → 301).

INTEGRATION SURFACE:
- New schema `directory` + migration → confirm number is next in the committed chain (after 0015).
- app_rt grants on directory tables = SELECT/INSERT/UPDATE/DELETE (mutable business data, owner-scoped);
  no trigger immutability needed here.
- public_routes.txt gains exactly the business-detail + covers(pincode) reads — justify each.
- No header/event-stream changes this spec.

DO NOT: no products yet (D17) · no reviews (D18) · no claim flow yet (D16) · no cross-module imports
(directory must not import identity — take user_id as a value) · no offset pagination.

NON-NEGOTIABLES: 1. covers(pincode) returns distance-ordered, keyset-paginated results (test w/ TN
pincodes incl. 641001) · 2. business writes owner-scoped (IDOR test) · 3. slug immutable + 301 on rename
(test) · 4. committed-tree migration chain linear.

THREAT MODEL: business-data IDOR (edit someone else's listing) → owned_by; scraping of covers() → rate
limits + keyset (no deep-offset enumeration).
DoD: covers(641001) test green; IDOR + slug tests green; PR → dev merged. `feat(d15): directory engine`.

═══════════════════════════════════════════════════════════════
## SPEC D16 — CLAIM FLOW + VERIFICATION-LITE QUEUE (~6h) · feat/d16-claims
═══════════════════════════════════════════════════════════════
CONTEXT: Businesses are seeded by us; owners "claim" them (the growth loop + a coins hook). Verification-
lite = doc upload → admin approve → verified badge. Admin UI on web-admin.

DO:
A. Tables: claims (business_id, claimant_user_id, status ENUM pending/approved/rejected, evidence_docs
   [media keys], created_at, decided_by, decided_at), verifications (business_id, method, doc keys,
   status, notes, decided_by).
B. Claim flow: user claims a business → claim pending → admin approves → business.owner_user_id set +
   verification_status→verified + **coins award (business_claim, once/business, via D13 award service,
   deterministic idem key claim:{business_id})** + notify claimant. Reject → notify + reason.
C. Media upload via D03 pipeline (presign → re-encode → EXIF-strip → media domain) for evidence docs.
D. Admin (web-admin): claim queue + verification queue (list, view docs, approve/reject with note) —
   role-gated (staff/super_admin), every decision audit-logged (D12).
E. Public: "Claim this listing" CTA on unclaimed business pages.

INTEGRATION SURFACE:
- **Coins hook** → calls D13 award via its service interface with an idempotency key; directory must NOT
  import coins internals — publish an event OR call the sanctioned award service boundary (match how D13's
  worker consumes events; prefer event: business.claimed → coins consumer awards). Confirm no double-credit
  (idem key business-scoped).
- **Audit** → every approve/reject writes an audit entry (D12 helper). Confirm chain stays clean.
- **Notify** → claimant notifications go through D12 preferences, not direct send.
- app_rt grants on claims/verifications tables (mutable, admin-decided).

DO NOT: no auto-approval · no coins award before approval · evidence docs never public · admin gates on
role (raw), consistent with D13's admin pattern.

NON-NEGOTIABLES: 1. business_claim coins awarded exactly once per business (idem test) · 2. every
decision audit-logged (chain-clean test) · 3. evidence docs behind auth (IDOR test) · 4. approve sets
owner + verified atomically.
THREAT MODEL: false claims (admin gate + evidence), coins-farming via claim/unclaim (once-per-business
idem, no unclaim path), evidence-doc leakage (auth-gated media).
DoD: claim→approve→coins+badge+notify E2E green; PR → dev. `feat(d16): claim + verification`.

═══════════════════════════════════════════════════════════════
## SPEC D17 — VERTICAL REGISTRY + SPEC-SCHEMAS + PRODUCTS + MEDIA (~6.5h) · feat/d17-registry-products
═══════════════════════════════════════════════════════════════
CONTEXT: THE versatility core (per Hub Structure doc). Built in basic form now so Milk.in products —
and every future vertical — ride it. Versioned JSONB spec-schemas drive product specs/filters without
per-vertical code. Plan mode first.

DO:
A. vertical_registry (schema directory): slug, name i18n, engines_enabled JSONB, nav_placement,
   status; seed the "milk" vertical.
B. spec_schemas (versioned): vertical_slug, version, fields JSONB ([{key,label i18n,type,unit,
   filterable,comparable,required,facet,group}]); validate-on-write against the active schema version.
C. products (schema directory or catalog): business_id, vertical_slug, schema_version, name, slug,
   specs JSONB (validated against schema), price_display (info-only string/number, NOT a transaction),
   media keys, status, moderation_status default pending (UGC mixin). Milk product schema seeded
   (type cow/buffalo/A2/toned/organic, fat %, pack size, price display).
D. Media pipeline hardening: reusable presign → server re-encode → EXIF-strip → serve-from-media-domain
   helper (D03) applied to product images; size/type validation.
E. Service + public read (product by slug, products for a business/vertical) — cursor-paginated,
   SSR-ready. Admin: schema CRUD (flag-gated).

INTEGRATION SURFACE:
- Media helper is shared infra (D16 evidence docs use it too) — factor ONE helper in shared/storage,
  don't fork a second. Confirm D16 and D17 call the same code.
- New tables → migration number next in committed chain; app_rt grants (products mutable + moderation).
- spec_schema validation is a shared contract every future vertical depends on — unit-test the validator
  hard (unknown field rejected, wrong type rejected, version pinning honored).

DO NOT: no transactions/checkout — price is DISPLAY only, do not scaffold cart/payment for goods ·
no per-vertical hardcoded product code (schema-driven only) · no offset pagination.
NON-NEGOTIABLES: 1. product specs validated against pinned schema version (test: old products keep
rendering after schema v2) · 2. media EXIF-stripped + served off app domain (test) · 3. one shared media
helper (no fork) · 4. committed-tree chain linear.
THREAT MODEL: malicious upload (re-encode + type/size), schema-injection via specs (server validation),
stored XSS via product text (escape on render).
DoD: schema validate + media + versioning tests green; milk vertical seeded; PR → dev.
`feat(d17): registry + products`.

═══════════════════════════════════════════════════════════════
## SPEC D18 — REVIEWS + LEADS ENGINE (~6.5h) · feat/d18-reviews-leads
═══════════════════════════════════════════════════════════════
CONTEXT: Two shared engines. Reviews = polymorphic, login-gated, moderated, coin-hooked. Leads = the
lead-gen heart (contact + milk_subscription types), pincode×category routed to business inboxes.
Threat focus: scraping → contact-reveal caps.

DO:
A. Reviews (schema directory or reviews): reviews (author_user_id, target_type ENUM business/product/
   vendor, target_id, rating 1–5, body i18n, moderation_status default pending), ratings aggregation
   (cached avg + count per target). Login-gated post; moderation queue (admin approve→visible + **coins
   award review_approved via event, 5/week cap** per D13 rules) ; one review per user per target.
B. Leads (schema leads): inquiries (type ENUM contact/milk_subscription, from_user_id nullable [guest
   allowed], business_id, payload JSONB {message | milk qty/type/pincode/schedule}, status ENUM
   new/responded/closed, pincode, category), routing service (match by coverage(pincode)×category →
   target business inbox), responses (inquiry_id, business_user_id, body, created_at), response-time
   stat per business.
C. **Contact-reveal caps** (anti-scraping): revealing a business phone/whatsapp is login-gated + daily
   per-user cap + logged (DPDP-aligned reveal log). Guests can submit a lead but not bulk-reveal contacts.
D. Business inbox UI (in Business Console shell — but shell lands D20; here expose the API + a minimal
   inbox list) + submitter status view. Notify both sides via D12 on new lead / response.

INTEGRATION SURFACE:
- Coins: review_approved award via EVENT (reviews emits review.approved → coins consumer), not a direct
  import. Confirm cap (5/week) enforced by rules engine, idem key review:{review_id}.
- Notify: lead + response notifications via D12 preferences.
- Reveal log is a PII-adjacent surface — ensure phone never logged in plaintext (extend D05 PII filter).
- Migration chain + app_rt grants for new tables.

DO NOT: no payment in leads (pure routing) · reviews default pending (no auto-publish) · contact reveal
never bypasses cap · no offset pagination on inbox/lists.
NON-NEGOTIABLES: 1. one review per user per target + pending default (tests) · 2. review_approved coins
capped 5/week (test) · 3. contact-reveal cap enforced + reveal logged w/o plaintext phone (tests) ·
4. lead routes only to businesses covering that pincode (test w/ 641001).
THREAT MODEL: review spam/brigading (login + one-per-target + moderation), contact scraping (reveal caps
+ login + log), lead-inbox IDOR (owned_by on inbox), coins-farming via review churn (approved-only + cap).
DoD: routing + reveal-cap + review-cap tests green; PR → dev. `feat(d18): reviews + leads`.

═══════════════════════════════════════════════════════════════
## SPEC D19 — SEARCH (MEILISEARCH) + LOCATION CONTEXT (~5.5h) · feat/d19-search-location
═══════════════════════════════════════════════════════════════
CONTEXT: Unified typo-tolerant search over directory + products, per-site indexes, event-driven reindex.
Plus the global location context (profile→GPS→pincode→IP) that personalizes everything, with a header
switcher. [BG] Coimbatore vendor seed runs alongside.

DO:
A. Meilisearch: indexers consuming domain events (business.created/updated, product.created/updated,
   claim.approved) → upsert to per-site indexes (milk index = milk-vertical businesses/products +
   coverage-aware); delete on soft-delete. Unified search API (query, filters, geo/pincode boost),
   cursor-style pagination.
B. Location context service: resolve order profile.location → GPS (client-provided, consented) →
   pincode entry → IP (state-level fallback); persist choice on AgriID profile (D11). Exposes current
   location to SSR + client.
C. Header LocationPill switcher (packages/ui, via AuthCluster integration point) — change pincode/
   district; shared across all apps; writes to profile.
D. Search UI shell (SearchBar wired to API) on web-milk; results ordered by location relevance.
E. [BG] Coimbatore-region vendor seed dataset normalized into import CSVs (used D27).

INTEGRATION SURFACE:
- **Event-driven reindex** consumes the SAME Redis Streams events other modules emit — enumerate every
  event the indexer listens to and confirm producers actually emit them (D15/D16/D17). This is a classic
  seam: indexer silently stale if an event isn't published.
- Location switcher extends AuthCluster (header) — do NOT add a second location widget; integrate with
  the existing header cluster (the D13 duplicate-pill lesson).
- Meilisearch is a new compose service — add to docker-compose.dev.yml; connects with its own key.

DO NOT: no Elasticsearch (Meili per Constitution) · no PII in search index (no phone/email indexed) ·
no offset paging.
NON-NEGOTIABLES: 1. reindex is event-driven + eventually-consistent (test: create business → appears in
index) · 2. location resolution order correct (test each fallback) · 3. one location switcher in header ·
4. no PII fields in any index (assert index schema).
THREAT MODEL: index poisoning via unmoderated content (index only approved/active), PII leak via search
(field allowlist), location spoofing (server trusts profile/pincode, GPS advisory).
DoD: create→searchable test green; fallback-order tests green; PR → dev. `feat(d19): search + location`.

═══════════════════════════════════════════════════════════════
## SPEC D20 — BILLING (RAZORPAY, FLAGGED) + DUNNING + BUSINESS CONSOLE SHELL (~7h) · feat/d20-billing
═══════════════════════════════════════════════════════════════
CONTEXT: Money-in path (businesses → platform: subscriptions only, no goods). Razorpay KYC on hold →
entire billing behind feature flag billing_enabled=false (seeded false in D03). Build complete, ship dark.
Includes dunning (v5 patch). 🔍 line-by-line money-path review. Plan mode first.

DO:
A. Tables (schema billing): subscriptions (business_id, tier, status ENUM active/past_due/canceled,
   current_period_end, razorpay_sub_id), invoices (subscription_id, amount, status, razorpay_invoice_id,
   pdf_key), payment_events (raw webhook log, idempotent by provider event id).
B. Razorpay integration (behind flag): create subscription, **signature-verified idempotent webhooks**
   (verify HMAC, dedupe by event id, process once), invoice sync. Never store card data.
C. **Dunning** (v5): on failed payment → status past_due → retry schedule (config) + grace window +
   dunning notifications (D12) → cancel on exhaustion. All timers config-driven, flag-gated.
D. Reconciliation job: nightly compare local vs Razorpay state, alert on mismatch.
E. **Business Console shell** (web-admin-adjacent, but business-facing): one dashboard, modules light per
   role/tier — subscription & invoices view, and mount points for leads inbox (D18), listings (D15),
   products (D17). Placeholder pricing tiers OK (real numbers when Pricing v1 lands, v5 Part 2).

INTEGRATION SURFACE:
- billing_enabled flag gates ALL endpoints + webhooks + UI (test: flag off → 404/hidden, no live calls).
- Webhook endpoint is public + signature-gated → public_routes.txt entry, justify; PII filter covers
  any payload logging.
- Business Console is the shell D18/D15/D17 UIs plug into — define the mount contract so later specs
  extend, not fork (the AuthCluster lesson applied to dashboards).
- app_rt grants; payment_events append-only-ish (dedupe), audit-log admin billing actions.

DO NOT: no goods/checkout ever · no card storage · no live Razorpay calls while flag off · webhooks must
be idempotent (dedupe test) · money-path is sensitive code — human line review required.
NON-NEGOTIABLES: 1. webhook signature verified + idempotent (replay test = one effect) · 2. flag off =
zero live billing surface (test) · 3. dunning transitions correct (past_due→retry→cancel test) ·
4. reconciliation detects an injected mismatch.
THREAT MODEL: webhook forgery (HMAC), replay (dedupe), state drift (reconciliation), premature charging
(flag gate).
DoD: signature+idempotency+dunning+flag-off tests green; 🔍 money path read; PR → dev. `feat(d20): billing + dunning`.

═══════════════════════════════════════════════════════════════
## SPEC D21 — ADS ENGINE v1 + OPS CONSOLE (~6.5h) · feat/d21-ads-ops
═══════════════════════════════════════════════════════════════
CONTEXT: Ads = the neutral monetization (labeled sponsored placements, never pay-to-rank organic).
v1: campaigns/creatives/slots, geo (district/pincode) targeting, approval queue, partitioned
impression/click tracking. Ops Console = unified moderation + feature flags for admins.

DO:
A. Tables (schema ads): campaigns (advertiser_business_id, name, status, budget_display, flight dates),
   creatives (campaign_id, media keys, copy i18n, target_url), placements (slot key, campaign_id,
   geo target JSONB {state/district/pincode}, status), impressions + clicks (PARTITIONED by day — high
   volume; append-only). Approval queue (creatives pending → admin approve).
B. Serving: given (slot, location) → eligible approved placements, frequency-capped, share-of-voice
   rotation; every ad render tagged "Sponsored" (labeling enforced in the component contract).
C. Tracking: impression/click beacons → partitioned tables; dedupe within a short window; counts
   surfaced to advertiser later (D55 full self-serve; here internal/admin view).
D. **Ops Console** (web-admin): unified moderation queue skeleton (reviews from D18, claims from D16,
   creatives here — one queue, typed items), feature-flag switches (billing_enabled, ads_enabled, coins
   rules), kill switches.
E. ads_enabled flag gates serving.

INTEGRATION SURFACE:
- **Unified moderation queue** is the convergence point for D16 claims + D18 reviews + D21 creatives —
  define ONE queue abstraction (typed item source) so D96+ (forum) and Stage E (classifieds) extend it,
  not fork it. This is the biggest shared-surface decision of the sprint — get the abstraction right.
- Partitioned tables: confirm partition creation is automated (a cron/maintenance job or default
  partition) so inserts never fail on a new day.
- app_rt grants; impressions/clicks append-only pattern.
DO NOT: no pay-to-rank of organic results (ads are separate labeled slots) · unlabeled ads forbidden ·
no offset paging · serving off when ads_enabled=false.
NON-NEGOTIABLES: 1. every served ad carries a "Sponsored" label (component + test) · 2. geo targeting
matches only in-scope locations (test 641001) · 3. impression/click partition insert works across a day
boundary (test) · 4. one moderation queue abstraction (claims+reviews+creatives flow through it).
THREAT MODEL: click fraud (dedupe + later rate analysis), ad-as-XSS (creative copy escaped, target_url
validated), organic-integrity erosion (hard separation labeled slots).
DoD: labeling + geo + partition + unified-queue tests green; PR → dev. `feat(d21): ads + ops console`.

═══════════════════════════════════════════════════════════════
## SPEC D22 — SPRINT-2 HARDENING + GATE 3 (~6h) · feat/d22-sprint2-hardening
═══════════════════════════════════════════════════════════════
CONTEXT: Adversarial + integration-seam audit of D15–D21, then GATE 3, then promote → v0.3.0. No new
features. This sprint added MANY shared surfaces (media helper, coins events, moderation queue, Business
Console, search reindex, billing flag) — the audit weights seams heavily, per the D13 lesson.

PRE-FLIGHT:
- `git status` clean, origin/dev == local dev before branching.
- Confirm backend-storm (and any other slow jobs) are REQUIRED status checks.

PART A — ADVERSARIAL + SEAM AUDIT (fresh session → docs/security/sprint2-audit.md):
A1. **Committed-tree migration chain** across all Sprint-2 migrations — no dup revisions, filename==internal
    revision, linear from 0015. (The exact D13 bug class.)
A2. **app_rt grant matrix** across new schemas (directory, leads, billing, ads): correct grants; any
    accidental UPDATE/DELETE on append-only tables (impressions/clicks/payment_events); any worker/compose
    service connecting as `app` instead of app_rt.
A3. **Event-stream contract**: enumerate every event produced (business/product/claim/review) and every
    consumer (search indexer, coins awards) — any consumer that breaks on an unexpected event? any
    producer a consumer expects but that isn't emitted (stale index / missing coins)?
A4. **Shared component/console seams**: one location switcher + one coins pill in headers (no regression);
    one unified moderation queue (claims+reviews+creatives); Business Console mount contract honored.
A5. **Shared media helper**: D16 + D17 use the same presign/re-encode/EXIF path (no fork).
A6. Generic surface: directory IDOR, claim-farming, reviews spam, **leads contact-scraping + reveal caps**,
    billing webhook forgery/replay + flag-off leakage, ads labeling/click-fraud, uploads.

PART B — FIX Critical/High; decide any deferrals with written reason in the audit doc.

PART C — FULL SUITE + MANUAL + COMMITTED-TREE:
- All module suites + cross-module E2E · manual: scripted lead-scrape attempt (reveal cap holds),
  webhook replay (one effect), ad geo-mismatch (no serve).
- Committed-tree verification: git archive HEAD → scratch → alembic loader + suite green there.

PART D — GATE 3 (record docs/gates/gate3.md, checked + dated):
☐ E2E: user registers → claims a business → (billing flag off, so) subscribes-path reachable but gated →
  receives a routed lead → responds — full loop green
☐ covers(pincode) + lead routing correct for 641001
☐ contact-reveal cap holds under scripted scrape
☐ billing flag OFF = zero live billing surface; webhook idempotent when on
☐ every served ad labeled Sponsored; geo targeting correct
☐ search reflects new/approved content (event-driven)
☐ committed-tree migration chain linear; app_rt grants correct; no service connects as `app`
☐ one location switcher, one coins pill, one moderation queue (no duplicates)
☐ public_routes.txt hand-reviewed; audit verify_chain clean; git status zero AM

PART E — PROMOTE: PR feat/d22 → dev (all checks green) → merge → PR dev→main (human) → merge →
`git tag v0.3.0 && git push origin v0.3.0`.

NON-NEGOTIABLES: zero Critical/High at tag · committed-tree verified · gate3.md complete+dated ·
v0.3.0 from main · then request Milk.in build pack (D23–D32).