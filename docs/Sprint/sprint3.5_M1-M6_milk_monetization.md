# SPRINT 3.5 — MILK MONETIZATION (M1–M6) · pre-launch, post-D30
# ═══════════════════════════════════════════════════════════════
# STANDING RULES (every session):
#   • Launch is DEFERRED until this sprint is e2e green. D30's DLT decision + audit fixes carry forward.
#   • The ad engine is ONE SHARED MODULE (extends D21). Milk.in is its first *configuration*.
#     TheOrganic.in and Agri.in must be able to adopt it with config only — zero engine code. M6 proves this.
#   • NAMING: TheOrganic.in replaces OrganicStore.in everywhere (organicstore.in = future selling venture,
#     out of scope). Update any spec/text encountered.
#   • ATOMIC DESIGN from M1 onward for ALL new frontend code: tokens → atoms → molecules → organisms →
#     templates. Folder structure: components/{atoms,molecules,organisms}. Do NOT retro-refactor shipped code.
#   • Labels: paid placement = "Sponsored" (always visible, ASCI disclosure). "Recommended" = organic
#     ranking ONLY (verified + rating + response-time). Never blur the two — trust is the product.
#   • Constitution unchanged: SecureRouter, owned_by(), UUIDv7, append-only ledgers, cursor pagination,
#     schema-driven config, tokens-only styling, Lighthouse ≥90 gate, same-day merge to dev.
#   • git status zero AM before every commit · committed-tree verify after conflict resolution.
#   • Sensitive code this sprint (billing, campaigns, delivery, creatives): line-by-line human review +
#     adversarial second pass — no deadline override.= 

═══════════════════════════════════════════════════════════════
## SPEC M1 — FULL PRODUCT TAXONOMY + VERIFIED-FIRST + ONBOARDING
   (~5.5h) · feat/m1-taxonomy-verified
═══════════════════════════════════════════════════════════════
CONTEXT: Milk.in currently exposes basic milk types. Expand to the full dairy taxonomy as D17 spec-schema
VALUES (config, not code), surface them on home, rank verified brands on top, and open the front door for
brand onboarding. Item 4 (brand sells one or all products) is verified by test — catalog already supports it.

DO:
A. Taxonomy (D17 vertical registry, admin/config): add category values — milk (cow/buffalo/mixed), ghee,
   paneer, milk powder, yogurt, lassi, curd, buttermilk, cheese, butter, cream, khoa, flavoured milk.
   Each value carries i18n labels (EN/TA/HI JSONB) + icon key. NO hardcoded lists anywhere.
B. Home category tile row (organism ← molecule CategoryTile ← atoms Icon/Label): icon-first, EN+TA/HI,
   tap → category page (auto-generated per schema value, ISR + JSON-LD, thin-pincode noindex rule holds).
C. Verified-first ranking: listing/browse sort = verified DESC, then existing relevance (rating,
   response-time, coverage). Applies to category pages, covers() results, search re-rank hook (D19).
D. "List your dairy business" CTA: header + footer + zero-coverage empty state → existing D16 claim/create
   flow via Business Console. A door, not a new flow.
E. Seed: extend D27 Coimbatore seed so every category value has ≥1 listing; TA/HI strings complete.

INTEGRATION SURFACE: schema values flow automatically to filters (D23), profiles (D24), dashboard (D26),
search facets (D19) — verify each picks up new values with zero code. Adding "khoa" later must light up
everywhere. Ranking touches directory queries only — no search index rebuild.
DO NOT: no hardcoded category list · no new tables · no retro-refactor of shipped components · no
"Recommended" label anywhere in this spec (that's M3's rule).
NON-NEGOTIABLES: 1. add-a-schema-value test: new value appears in home tiles + filters + category page
with zero code (test) · 2. verified brand outranks unverified same-relevance (test) · 3. brand with ONE
product and brand with ALL products both render correctly on profile + category pages (test — item 4) ·
4. Lighthouse ≥90 holds on home with tile row.
THREAT MODEL: fake verification pressure (D16 queue is the only path to the badge), seed quality
(validation + review), i18n gaps shipping English-only tiles.
DoD: 4 tests green · every category value seeded + translated · PR → dev. `feat(m1): dairy taxonomy +
verified-first + onboarding CTA`.

═══════════════════════════════════════════════════════════════
## SPEC M1.5 — TRUST & SAFETY + PROFILE POLISH (~4h)
   · feat/m1x-trust-safety
═══════════════════════════════════════════════════════════════
CONTEXT: User-side reporting + admin-side enforcement, plus two profile gaps: brand About section and
member-since date. Reporting rides the EXISTING flags/moderation queue (Sprint 2, Ops Console) — extend,
don't build a second reporting system. Admin verification (D16) remains the ONLY path to the verified
badge — restated here because enforcement and verification share the same admin surface.

DO:
A. Report flow (user-facing): "Report" action on brand/shop/vendor profile pages (D24) — molecule
   ReportDialog: reason picker (fake listing · wrong info · abusive · fraud/scam · other+text, i18n) +
   optional detail. Login required (rate-limited per user per target). Writes a flag into the EXISTING
   unified moderation queue. Reports are VISIBLE ONLY in the Ops Console — never public, never shown to
   the reported vendor with reporter identity (reporter anonymous to vendor, visible to admin).
B. Admin enforcement (Ops Console, extend business mgmt UI from D16): actions on a business —
   suspend (delisted: hidden from browse/covers()/search/ads; profile URL → 410-style "unavailable";
   dashboard shows suspension notice + reason to owner) and disable (hard-off: owner dashboard access to
   it locked, all serving stops incl. active ad campaigns → auto-paused, no refund logic v1 — flag for
   manual handling). Both append to an enforcement audit log (who, when, why, prior state). Reinstate
   action restores prior state. Suspension does NOT delete data (soft-state, Constitution soft-delete).
C. Brand About section: description JSONB (EN/TA/HI) on business profile — editable in D26 dashboard
   (plain text v1, length-capped, no HTML), rendered on D24 public profile + included in LocalBusiness
   JSON-LD description field.
D. Member-since: user profile/dashboard shows "Member since {month year}" from AgriID created_at.
   Vendor public profiles show "On Milk.in since {month year}" (business created_at) — trust signal.
E. Search/index hooks: suspend/disable emits D12 event → D19 indexer removes from Meilisearch; ads
   delivery (M3, when built) must check business status at serve time — leave a status accessor
   is_servable(business_id) for M3 to consume.

INTEGRATION SURFACE: flags → EXISTING moderation queue (one queue, one admin surface). Enforcement
status must propagate to: browse/covers() (D15), search (D19 via events), profiles (D24 → unavailable
page), dashboard (D26 → locked/notice), and later M3 ad serving via is_servable(). Audit log append-only.
DO NOT: no second reporting/moderation system · no public visibility of reports or report counts · no
hard delete on suspend/disable · no reporter identity exposure to vendors · no HTML in About v1.
NON-NEGOTIABLES: 1. report lands in Ops queue and is invisible everywhere public (test) · 2. suspended
business vanishes from browse + covers() + search, profile shows unavailable, owner sees notice (test) ·
3. disabled business: owner dashboard locked + campaigns auto-paused (test; campaign part activates once
M5 exists — write the test against is_servable now) · 4. enforcement writes audit row; reinstate
restores prior state (test).
THREAT MODEL: report brigading to bury competitors (rate limits + admin sees reporter patterns +
enforcement is HUMAN decision, never auto-suspend on report count), reporter retaliation (anonymity to
vendor), admin action without trail (append-only audit), suspended vendor's ads still serving (serve-time
status check — the M3 seam).
DoD: 4 tests green · PR → dev. `feat(m1x): reporting + enforcement + profile polish`.

═══════════════════════════════════════════════════════════════
## SPEC M2 — AD SURFACES: GLOBAL SLIDING BANNER + SLOT SYSTEM
   (~5.5h) · feat/m2-ad-surfaces
═══════════════════════════════════════════════════════════════
CONTEXT: D21 engine (campaigns/creatives/slots/geo/approval/partitioned tracking) is live but unmounted.
Mount it: one AdSlot primitive, a global sliding head banner on EVERY page, plus page-level slots.
Components are vertical-agnostic (engine reusability starts here).

DO:
A. Atoms/molecules: AdImage (sanitized img-only v1, no HTML creatives), SponsoredBadge (always visible);
   molecule AdSlot(slot_key, context{pincode, category?}) → fetches approved creative from D21, tracks
   impression (viewport-visible, not on-mount) + click via D21 partitioned tracking; empty → collapses,
   reserved aspect-ratio box while loading (zero CLS).
B. Organism AdCarousel: sliding head banner — max 5 creatives, weight/rotation from D21, swipe on mobile,
   autoplay ON with 6s interval + pause-on-touch + prefers-reduced-motion respected, lazy beyond slide 1
   (rural data reality: slide 1 eager, rest lazy).
C. Mount in layout shell (renders on ALL pages incl. home): slot_key milk_global_header. Page slots:
   milk_home_hero, milk_category_banner (context = category value), milk_search_inline, milk_profile_footer.
D. Slot registry entries in D21 via Ops Console (config). Naming convention {vertical}_{placement} so
   theorganic_global_header etc. are pure config later.
E. House-ad creatives seeded per slot ("Post your need", "List your business") — surfaces never empty.

INTEGRATION SURFACE: creatives ONLY where moderation_status=approved (component-level guarantee, not
page-level). Tracking writes ONLY to D21 partitioned tables. Category banner reads M1 schema values —
new category ⇒ targetable inventory automatically. Layout shell touch is one-of-each header-widget
verified across all Milk pages.
DO NOT: no HTML/script creatives v1 · no third-party ad scripts · no autoplay without reduced-motion
respect · no layout shift · no tracking on render (viewport-visible only) · no new tracking tables.
NON-NEGOTIABLES: 1. unapproved/pending creative NEVER renders (test) · 2. impression fires only on
visibility + click rows land in D21 partitions (test) · 3. CLS ≈ 0 with slots empty, loading, and full
(measured) · 4. Lighthouse ≥90 on home with carousel live.
THREAT MODEL: creative XSS (img-only + sanitize + CSP), click fraud (D21 rate caps + dedupe window),
pending-creative leak, ad-blocker breaking layout (collapse gracefully).
DoD: 4 tests green · house ads visible on all slots at 641001 · PR → dev. `feat(m2): ad surfaces +
global carousel`.

═══════════════════════════════════════════════════════════════
## SPEC M3 — DELIVERY: GLOBAL+LOCAL BLEND + SPONSORED LISTINGS
   (~6h) · feat/m3-delivery-sponsored
═══════════════════════════════════════════════════════════════
CONTEXT: Delivery logic. A user in any pincode sees the union of all-pincode (global) campaigns AND
their-pincode (local) campaigns, per slot, per category independently (item 8). Sponsored listings blend
into result lists per pincode × category or overall (item 6). Labeling law: item 7.

DO:
A. Delivery query (engine, D21 extension): eligible = approved ∧ active ∧ in-budget ∧
   is_servable(advertiser business — M1.5 status check, suspended/disabled never serve) ∧ (targeting.pincodes
   = ALL ∨ user_pincode ∈ targeting.pincodes) ∧ (targeting.categories = ALL ∨ slot category ∈
   targeting.categories). Weighted rotation: local gets a configurable boost factor over global (default
   2×) so village advertisers aren't drowned by national brands. Frequency cap per user-session per
   creative. Category dimension evaluated independently per slot instance.
B. Sponsored listings: new placement type sponsored_listing — vendor/brand card injected into category,
   covers(), and search result lists. Cap: max 2 per page, positions 1 and 6, always SponsoredBadge,
   never counted in organic result count, cursor pagination unaffected (injected at render layer, not in
   the cursor stream).
C. "Recommended" (organic ONLY): algorithmic rail = verified + rating + response-time + coverage
   freshness. Paid can NEVER buy the Recommended label (enforced in code: label source is ranking fn,
   not campaign data).
D. Anonymous users: pincode from LocationPill/GPS context (D19) drives local blend pre-login; on login,
   profile pincode takes over (item 8's signup/login case).
E. Delivery decisions logged (campaign_id, slot, pincode, category, why-served) — append-only, sampled —
   for advertiser analytics (M5) and dispute resolution.

INTEGRATION SURFACE: delivery is ENGINE code — zero Milk-specific logic (vertical comes in via slot_key +
category context). Sponsored injection touches list renderers from M1/D23/D19 — verify cursor pagination
byte-identical with sponsorship on/off. Reveal caps (D18) still govern contact actions on sponsored cards.
DO NOT: no paid influence on organic order (sponsored is injected, organic order untouched — test) · no
"Recommended" on any paid unit · no offset pagination sneaking in · no unbounded frequency (caps required).
NON-NEGOTIABLES: 1. blend test: global-only campaign + local campaign both serve at 641001; local-only
absent at 110001 (test) · 2. per-category independence: ghee campaign never serves on paneer page (test) ·
3. organic order identical with sponsorship enabled/disabled (test) · 4. every paid unit carries
SponsoredBadge (snapshot test).
THREAT MODEL: label laundering (paid posing as organic — the #1 trust risk), budget race on concurrent
serves (atomic decrement), geo spoofing for cheap-tier arbitrage (serve-side pincode from context, not
client claim), delivery-log PII (pincode ok, no user identifiers beyond hashed session).
DoD: 4 tests green · PR → dev. `feat(m3): delivery blend + sponsored listings`.

═══════════════════════════════════════════════════════════════
## SPEC M4 — AUTOMATIC PINCODE TIERS (~5h) · feat/m4-pincode-tiers
═══════════════════════════════════════════════════════════════
CONTEXT: Classify every Indian pincode T1–T5 (metro → extreme rural) with ZERO manual intervention:
v1 by population, v2 (auto-upgrading, later) by population + registered users. Tiers drive the M5 rate
card and future analytics. Engine-level (schema: geo) — all verticals share it.

DO:
A. Data: import census population mapped to pincodes (village/ward → pincode aggregation; document the
   approximation honestly in the migration). Table geo.pincode_tiers: pincode PK-ish (unique), population,
   tier SMALLINT, user_count, computed_at, method ('population'|'population+users'). Append-only history
   table for tier changes (audit).
B. Classification job: percentile thresholds over population distribution (T1 metros ≈ top 1%, T2 cities,
   T3 towns, T4 villages, T5 extreme rural — thresholds in config, not code). Idempotent, re-runnable.
C. User-count re-rank hook: nightly job recomputes user_count from AgriID profiles by pincode; when a
   pincode's users cross a configured threshold, method flips to population+users and tier can promote
   (never auto-demote — config flag). Fully automatic; admin override exists but nothing REQUIRES it.
D. Expose: tier available to delivery (M3 analytics), rate card (M5), Ops Console read view with
   distribution histogram.
E. TN pincodes verified complete (launch geo); pan-India rows load but stay dormant (Stage-B geo rule).

INTEGRATION SURFACE: geo schema only; delivery/rate-card read via one accessor fn (get_tier(pincode)) —
no direct table reads from other modules. Nightly job = D12 events/cron pattern, not a new scheduler.
DO NOT: no manual tier assignment as the primary path · no scraping population data from unlicensed
sources (use census/open data; record provenance in migration) · no auto-demote v1 · no blocking
delivery when a pincode has no tier row (default T4, log it).
NON-NEGOTIABLES: 1. 641001 classifies T2/T1 and a known village pincode classifies T4/T5 without any
manual step (test) · 2. unknown pincode → safe default, delivery unaffected (test) · 3. user-count
promotion fires when threshold crossed (test, synthetic users) · 4. tier change writes history row (test).
THREAT MODEL: bad source data mis-pricing ads (provenance + distribution sanity check in job), signup
farming to inflate a pincode's tier (threshold + verified-profile filter on user_count), tier flapping
(hysteresis: promote-only + min interval).
DoD: 4 tests green · TN coverage verified · PR → dev. `feat(m4): automatic pincode tiers`.

═══════════════════════════════════════════════════════════════
## SPEC M5 — ADVERTISER SELF-SERVE + RATE CARD + BILLING LIVE
   (~7h, split across 2 sessions if needed: console / billing)
   · feat/m5-advertiser-selfserve
═══════════════════════════════════════════════════════════════
CONTEXT: The "fully automated" half of item 11: a brand signs in, builds a campaign, pays, creatives go
to moderation, ads serve — no human in the loop except creative approval. Extends D26 dashboard +
un-darks D20 billing. Items 5 + 10 land here.

DO:
A. Campaign wizard (organism, in D26 Business Console): steps — objective (banner slot(s) ∨ sponsored
   listing) → categories (one ∨ multiple ∨ ALL — M1 schema values) → pincodes (one ∨ multiple ∨ ALL ∨
   by-tier "all T3 towns in TN") → schedule + budget (daily cap ∨ total) → creatives upload (D17 media
   pipeline: presigned, type/size, re-encode, EXIF-strip) → review + price → pay.
B. Rate card: price = f(slot type, tier, category multiplier) — config table, Ops-editable, versioned.
   Wizard shows itemized price live. CPM v1 for banners (impression-priced), flat weekly for sponsored
   listings — keep v1 simple; auction deferred.
C. Billing un-dark: billing_enabled=true in dev/staging; Razorpay TEST mode e2e — order → payment →
   webhook (signature-verified) → append-only billing ledger entry → campaign activates. Failed/refund
   paths + dunning (D20) wired. GST invoice PDF generated + emailed (Zoho).
D. Campaign lifecycle: draft → pending_payment → pending_moderation → active → paused/exhausted/expired.
   Budget decrement atomic at serve (M3). Advertiser can pause/resume; edits to creatives re-enter
   moderation.
E. Advertiser analytics (from M3 delivery log + D21 tracking): impressions, clicks, CTR, spend, by
   pincode + category. Money path: line-by-line human review + adversarial second pass (standing rule).

INTEGRATION SURFACE: wizard mounts in D26 shell (extend, don't fork). Payments through D20 billing module
ONLY (no direct Razorpay calls from ads code). Ledger append-only — campaign spend reconciles against
ledger, never against mutable state. Moderation = D21 queue in Ops Console (unchanged approval flow).
prod billing_enabled stays FALSE until launch-day decision.
DO NOT: no live-mode Razorpay this sprint · no skipping webhook signature verification · no mutable
balance column (ledger-derived only) · no campaign activation before BOTH payment ∧ moderation pass ·
no auction/bidding v1.
NON-NEGOTIABLES: 1. e2e: create → pay (test mode) → approve → serves at targeted pincode×category ∧
NOT elsewhere (test) · 2. forged/replayed webhook rejected (test) · 3. ledger sums = Razorpay test
transactions exactly (reconciliation test) · 4. campaign IDOR: owned_by on every campaign read/write
(test).
THREAT MODEL: payment webhook forgery/replay (signature + idempotency key), budget race (atomic
decrement, tested concurrent), campaign IDOR, price tampering (server-side pricing only — client shows,
server computes), moderation bypass via edit-after-approve (re-moderation on change).
DoD: 4 tests green · full wizard usable on mobile · PR → dev. `feat(m5): advertiser self-serve +
billing`.

═══════════════════════════════════════════════════════════════
## SPEC M6 — PORTABILITY PROOF + DELTA AUDIT + FREEZE (~6h)
   · feat/m6-portability-freeze
═══════════════════════════════════════════════════════════════
CONTEXT: Prove item 11 (one engine, config-only reuse), then re-freeze security AFTER all monetization
code. This replaces D30's freeze as the final pre-launch gate; D30's DLT decision + Cloudflare config
carry forward unchanged.

DO:
A. PORTABILITY PROOF (staging): create slot theorganic_global_header + one theorganic category value +
   one test campaign targeting it, via config/Ops Console ONLY. It must serve on a bare test page with
   ZERO engine/frontend-component code changes. Document the recipe → docs/ads/vertical-onboarding.md
   (this doc IS the deliverable TheOrganic.in and Agri.in sprints will follow).
B. Delta adversarial audit (fresh session → docs/security/milk-audit-m.md): money path (billing, webhook,
   ledger), creative sanitization + CSP, campaign/coverage IDOR, delivery-log privacy, tier-gaming,
   sponsored-label integrity. Fix ALL Critical/High — no gate soft-disable.
C. k6 re-run WITH ads serving: browse 500 concurrent + delivery query under load — p95 within budget
   (delivery adds a query per slot; verify caching strategy holds, add short-TTL cache if needed).
D. Full regression: D29 QA matrix + M1–M5 non-negotiables, one pass, documented.
E. FREEZE. → then D31 (collapsed: /opt/agri, compose -p agri on 3100/8100, five nginx blocks + certs —
   box already hardened; theorganic.in in DNS/nginx naming, NOT organicstore.in) → D32 launch checklist
   + promote v1.0.0-milk. prod flags at launch: billing_enabled = launch-day decision · sms per D30
   record.

INTEGRATION SURFACE: the portability proof is the integration test — if any step needs code, that's a
finding, fix the engine. Audit covers seams: M3 delivery ↔ D21 tracking, M5 billing ↔ D20 ledger,
M1 schema ↔ every consumer.
DO NOT: no code during portability proof (findings → fix engine, re-prove) · no launch with open High ·
no freeze before ALL M-specs merged.
NON-NEGOTIABLES: 1. theorganic test slot serves via config only (documented, reproducible) · 2. zero
Critical/High at freeze · 3. k6 with ads within budget · 4. regression pass documented.
THREAT MODEL: the audit is the threat model — plus "portability proof papered over with a hack" (the
doc must be followable by a fresh session cold).
DoD: proof doc + audit + k6 + regression green → FREEZE → proceed D31/D32. `feat(m6): portability +
freeze`.

───────────────────────────────────────────────────────────────
LAUNCH SEQUENCE AFTER M6: D31 (collapsed infra prep) → D32 (checklist → dev→main → tag v1.0.0-milk →
deploy → DNS cutover → watch). TheOrganic.in sprint (D33+) then starts by READING
docs/ads/vertical-onboarding.md — the engine arrives free.
⚠ CARRY-FORWARD FROM D30: the recorded DLT/SMS decision governs signup at launch. If gated, the flip-on
plan (signup enable when DLT clears) is a one-flag change — keep it that way.
