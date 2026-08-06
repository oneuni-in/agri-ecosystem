# Manual UI test guide — D01 → M4 (platform + milk.in)

Owner-facing walkthrough for hand-testing everything shipped in D23–D30 and M1 on a dev box.
Automated coverage for most of these journeys lives in `e2e/` (see
`docs/qa/d29-device-matrix.md` for what automation already proves and what is
hardware-only). This guide is the human pass: eyes on the UI, real clicks.

## Setup

```bash
docker compose -f docker-compose.dev.yml up -d      # API :8000, postgres :55432, redis, workers
pnpm --filter @agri/web-milk dev                    # :3000  consumer site (milk.in)
pnpm --filter @agri/web-agri dev                    # :3002  vendor console
pnpm --filter @agri/web-id dev                      # :3003  login/SSO
pnpm --filter @agri/web-admin dev                   # :3004  staff moderation (/ops)
```

Fresh DB only (from `backend/core`, venv python):
`alembic upgrade head` → `scripts/load_geo.py` → `scripts/seed_e2e_milk.py` →
`scripts/import_vendor_seed.py` (150+ Coimbatore vendors/brands; idempotent; `--dry-run` first) →
`scripts/seed_house_ads.py --enable-flag` → `scripts/seed_sample_media.py` (placeholder
images for ad creatives + up to 80 products, uploaded through the real media pipeline).

Accounts:
- Consumer: chan `+916374344282` (super_admin — also works for /ops).
- Vendor owner: `+919000000023` (owns "E2E Milk Vendor", covers 641001).
- Dev OTP is peekable/logged by the API console.

URL scheme (post-D28): everything is locale-prefixed (`/en`, `/ta`, `/hi`) and pincode
pages live at `/{locale}/{city}/{pincode}` — e.g. `http://localhost:3000/en/coimbatore/641001`.
Old `/en/641001` URLs 301 to the city form.

Gotchas: ISR caches public pages ~5 min (clear `apps/web-milk/.next/cache/fetch-cache`
to see data changes immediately); kill stray processes on ports 8000/3000-3003 if a
server misbehaves after a crashed session.

## Platform layer (D01–D22) — the foundation under milk.in

These are exercised implicitly by the milk sections below; this section tests them
head-on. Apps: web-agri `:3002` (agri.in consumer + console), web-id `:3003`
(identity hub), web-organic `:3001`, web-admin `:3004`.

### Identity, sessions, devices (D06–D10)

1. `:3003/account` — profile: AG- agri-id shown, handle, display name, language,
   pincode lookup (needs geo loaded — a broken lookup means run `load_geo.py`).
   Handle change: the free change is consumed at signup; a later change costs coins.
2. `:3003/devices` — log in from a second browser, both sessions listed; revoke the
   other one → that browser is signed out on next action. "Logout everywhere" kills
   both at once.
3. Cross-app SSO (D10): log in on milk.in `:3000` → open organic `:3001` → header is
   already logged-in (silent SSO); logout-everywhere signs out every app.
4. Wrong OTP: 3 bad codes → burn/lockout UX with a clear message, then recovery.

### Agricoins (D13)

1. `:3003/coins` — balance + ledger. Earn a row: submit a review on any business,
   approve it in `:3004/ops` → +coins (rule `review_approved`, capped 5/week);
   the CoinsBalancePill in the headers updates.
2. `:3004/coins` (staff) — coins admin: search a user, manual adjustment with a
   reason code → shows in the user's ledger with the reason.

### Claims & verification (D16) — on agri.in

1. `:3002/directory/businesses/aavin` (also `arokya`, `sakthi-dairy` — seeded
   ownerless, hence claimable) → "Is this your business?" card → claim form:
   upload 1–5 evidence photos (≤5MiB each; a 6th or oversized file is rejected).
2. `:3004/claims` (staff) → approve with a note → claimant now owns the listing
   (it appears under their `:3002/business` console) and the verified badge path
   opens. Reject requires a reason (≥3 chars).
3. IDOR: a different user cannot see or decide someone else's claim.

### Search freshness (D19)

1. `/en/search` on milk.in: typo query ("mlik", "panner") still finds results
   (Meilisearch typo tolerance).
2. Freshness: rename a product in the vendor console → within ~a minute (search
   worker consumes the event) the new name is searchable; the old one isn't.

### Notifications (D12)

1. `:3002/notifications` and `:3003/notifications` — the same in-app feed follows
   you across apps; mark-read state persists.
2. Every notification in the feed traces to a real event (lead, response, review
   decision, claim decision) — no orphan templates.

### Billing surface stays dark (D20)

1. `:3002/business/billing` — with the billing flag off this renders the
   "activation at launch" state: no payment inputs, no charge paths reachable.

### Admin & RBAC (D11, D21)

1. `:3004/users` (staff) — user search shows phone LAST-4 ONLY (never the full
   number), role assignment audited.
2. `:3004/businesses` — tier is ADMIN-set here (vendor console only records
   intent); suspend/reinstate lives in `/ops` enforcement.
3. A non-staff account opening any `:3004` page gets denied — no data leak in the
   denial.

### Design-system kitchen sink (D02)

1. `:3002/demo` — every token/component in one page (the Lighthouse-gated
   reference); nothing raw-hex, tap targets ≥44px, focus rings visible.

## D23 — Pincode home

1. `/en` → pincode hero; enter 641001 (or GPS).
2. `/en/coimbatore/641001` → covered state: heading, schema-driven milk-type chips,
   price banner ("Today in 641001: Cow ₹…"), distance-sorted vendor cards.
3. `?type=buffalo` chip filters; a type with no products → filtered-empty message + "see all".
4. Uncovered TN pincode → warm "no vendors yet" state + Notify me (submits → done state).
5. Non-TN pincode (110001) → out-of-area state + Notify me.

## D24 — Vendor profiles, tracked contact, map

1. On the pincode page: "🗺 Show map" → pins render at their coordinates and the map
   fits them (D29 fixed fitBounds). Pin click → card highlight + scroll; card click →
   pin recolors + flyTo.
2. Card Call/WhatsApp → profile `/en/directory/businesses/{slug}`: products + prices,
   delivery area (coverage pincodes), branches + hours, reviews. View-source: one
   `application/ld+json` LocalBusiness block (validator.schema.org to verify).
3. Logged OUT: "📞 Login to view contact" — page source contains NO phone number.
   Enquiry form still works as guest → "Enquiry sent".
4. Logged IN: reveal → Call/WhatsApp with `tel:`/`wa.me`. ~10 reveals in a day →
   "Daily reveal limit reached". Each first reveal per vendor/day also lands a
   `contact` lead in that vendor's inbox (attribution — check in D26 inbox).
5. Review: submit → "visible after moderation"; resubmit → "already reviewed";
   approve in :3004 `/ops` → appears publicly (allow ISR).

## D25 — Post my need

1. `/en/post-need` (CTA on home/pincode pages): litres, milk-type chips, prefilled
   pincode, schedule, delivery-time, optional voice note (records + stores; no
   transcription — shell only). Guest → inline phone+OTP → progressive account.
2. `/en/my-needs`: the need, status `new`, voice note attached.
3. Uncovered pincode → no-coverage handling (never a silent success).
4. Loop closes via D26: vendor responds → bell notification + response under the
   need → accept / mark fulfilled → `closed`.

## D26 — Vendor dashboard (:3002/business, as vendor owner)

1. Listings: edit listing, delivery windows, coverage editor. Add a pincode →
   that pincode's milk.in page now lists the vendor (covers() live); remove → reverts.
2. Products: schema-driven create → pending → approve in `/ops` → public. Bad input
   → field-level 422 messages.
3. Inbox: D25 needs + D24 contact leads, type filter, need details incl. voice note.
   Respond → consumer notified (bell + push if subscribed). Response-time stats +
   slow-responder nudge.
4. Analytics: profile views (view beacon), reveals, leads — by-pincode breakdowns.
5. Premium: select tier → "activate at launch" (billing flag off — no charge, billing
   surface stays dark). Tier drives priority placement in results.
6. IDOR: an account owning nothing gets no vendor data; foreign business ids → 404.

## D27 — Dairy directory, brands, i18n, seed

1. Locale switcher: `/en/...` ↔ `/ta/...` ↔ `/hi/...` — fully translated chrome AND
   seeded content (descriptions in 3 locales); query params survive switching.
2. Category landings `/en/c/{category}` (dairy-farm, feed-supplier, cooperative, vet,
   equipment…): landing + covers-based browse at your pincode; empty-at-pincode and
   fetch-error states are distinct.
3. Pincode page shows category cross-links into `/c/...`.
4. Brand pages (Aavin/Hatsun-style seeds): brand variant of the profile with products
   + "shops near you" (nearest branches w/ distance) + category cross-links.
5. Seed sanity: pincode pages feel like a real marketplace (150+ businesses).
6. `/en/search`: results; "load more" keeps the locale prefix.

## D28 — PWA + pincode SEO

1. Manifest + SW active (DevTools → Application). Install: desktop omnibox icon /
   Android install card / iOS A2HS hint. Launches standalone.
2. Offline shell: load a pincode page, go offline, reload → last-seen prices +
   helpline numbers (never the browser error page). Cache Storage holds public data
   only — no PII.
3. Push: subscribe card (notifications area) → enable/disable; vendor response →
   push arrives (localhost is a secure context); preference off → no push.
4. SEO: covered pincode page indexable + ItemList JSON-LD + hreflang; zero-vendor
   page self-noindexes; `/sitemap.xml` lists covered city/pincode URLs; `/robots.txt`.
5. Redirect hygiene: old `/en/{pincode}` → 301 city URL; renamed business slug →
   old profile URL 301s.
6. Low-data mode toggle: low-quality/lazy images (ads lazy), persists across reloads.

## D29 — QA layer itself

1. Full automated matrix: `npx playwright test --config e2e/playwright.config.ts`
   (~35 min: desktop + mobile-chrome + mobile-safari device projects).
2. Real-hardware checklist: `docs/qa/d29-device-matrix.md` — Android install+push,
   iOS 16.4+ web-push, physical 3G feel, TA/HI rendering on low-end screens.
   (WebKit-over-http can't set Secure cookies — those checks are hardware-only.)
3. Spot-check D29's four fixes: map fits pins on open; category chips ≥44px;
   TA/HI contrast + no nested-interactive cards; pincode page usable on throttled 3G.

## D30 — Security freeze

1. Signup gate: the two-layer gate holds — an un-invited/ungated fresh phone gets the
   launch-gate response on signup, existing accounts log in normally (dev flags may
   open the gate locally; check settings before filing a bug).
2. Rate limits: hammer a public endpoint (reload a pincode page rapidly ~30x or curl
   the covers API in a loop) → 429s appear, then recover after the window. Limits are
   per-path — one throttled path must not lock out the others.
3. No seed/test credentials work against anything but dev: OTP peek routes 404 unless
   `OTP_TEST_PEEK=true`.

## M1 — Product taxonomy + verified-first + onboarding CTA (:3000)

1. Home `/en`: category tile row (milk, curd, ghee, paneer, …) — every tile 44px+,
   localized in TA/HI.
2. Tiles → `/en/p/{category}` auto-generated category pages (e.g. `/en/p/ghee`):
   ISR, populated from the taxonomy, indexable.
3. Pincode page: schema-driven category chips; `?product_category=ghee` filters the
   vendor list server-side (covers() SQL, not client filtering). Filtered views are
   noindex and the canonical stays the unfiltered page.
4. Verified-first: on any pincode page and in `/en/search`, ✔ Verified businesses
   rank above unverified ones; within each block, distance order still holds.
   Paginate past the verified/unverified boundary — no dupes or gaps (4-field cursor).
5. Product create (vendor console, D26 walk): `category` is now REQUIRED — the form
   offers the schema values and rejects a missing category (schema v2 repin).
6. "List your dairy business" CTA: header, footer, and empty states → lands on the
   vendor console (`NEXT_PUBLIC_CONSOLE_URL`); 44px target.
7. Hidden verticals stay hidden: the public vertical-schema route serves the milk
   taxonomy but must NOT enumerate unlaunched verticals.
8. Seed: every dairy category has at least one seeded product (incl. the ghee product
   on the covered vendor), so no category page or chip renders empty at 641001.

## M1.5 — Trust & safety (merged)

1. Report flow: on a profile, "Report" → submit a reason → recorded, but the business
   is NEVER auto-suspended (reports queue for staff; check in :3004 /ops).
2. Enforcement: in /ops suspend a business → its public profile serves **410 Gone**
   (not 404), it drops out of covers()/search, and its ads stop serving (is_servable
   fail-closed). Reinstate → everything returns.
3. Disabled account: a disabled vendor hitting the console gets the locked-out screen,
   not a crash.

## M2 — Ad surfaces (:3000 + :3004/ads, this branch)

Slots: `milk_home_hero` (carousel), `milk_global_header`, `milk_category_banner`,
`milk_search_inline`, `milk_profile_footer`. House ads are seeded by
`scripts/seed_house_ads.py` (e2e bootstrap runs it with `--enable-flag --reset-caps`).

1. House ads visible: at `/en` (hero carousel) and on pincode/category/search/profile
   surfaces at 641001 — every ad carries the ★ Sponsored badge, images only.
2. Carousel: autoplays, swipes; with OS "reduce motion" on → NO autoplay.
3. Impressions are visibility-gated: DevTools Network → load a page with a
   below-the-fold slot → no impression beacon until you scroll it into view; then
   exactly one fires. Click an ad → click beacon lands (D21 partitioned tables).
4. CLS ≈ 0: empty slot, loading slot, and full slot must not shift the page
   (fallback reserves the box; toggle an ad-blocker → layout collapses gracefully).
5. Admin (:3004/ads): create a campaign (advertiser business UUID via
   `GET :8000/directory/businesses/{slug}` → `business.id`), add a creative with
   slot key + category + pincode targeting. While the creative is PENDING it must
   never render on milk.in; approve it → it serves at the targeted pincode/category.
6. CSP: console shows no third-party script loads on ad surfaces; creatives are
   images only.
7. Perf: home Lighthouse ≥0.90 WITH the carousel live (the #45 fix — inline CSS +
   SVG Devanagari — raised the CI gate back to 0.90; keep it there).

## M3 — Delivery blend + sponsored listings (:3000 + :3004/ads, this branch)

Engine: global (ALL-pincode) and local campaigns blend per slot; local gets a 2×
rotation boost (`ADS_LOCAL_BOOST`). Campaigns can carry a serve-credit budget
(blank = unlimited); serves decrement it atomically. Sponsored listings are a new
slot `milk_sponsored_listing` injected into result lists at render (positions 1
and 6, max 2). Seed with `scripts/seed_house_ads.py --with-sponsored-listing`
(the e2e bootstrap passes it) to get a global house listing card.

1. Blend: create a local campaign (placement targeting pincodes `["641001"]`) plus
   the seeded global house card → both serve at `/coimbatore/641001`; at a non-TN
   pincode (e.g. 110001) only the global one serves.
2. Sponsored listing card: first cell of the "Local vendors" grid (and position 6
   when ≥2 ads) carries ★ Sponsored, links out with `rel="nofollow sponsored"`,
   fires visibility-gated impression + click beacons. Organic vendor count and
   the load-more cursor are identical with the ads flag on/off; the JSON-LD
   ItemList never mentions the ad. Same injection on `?category=` browse and
   `/search` results.
3. Recommended rail: on the unfiltered landing view, verified vendors with
   ratings/fast lead responses/fresh coverage appear under "⭐ Recommended"
   (max 3). Flip a vendor to premium or give it a campaign → rail order must NOT
   change (paid can never buy the label). Chip-filtered and cursor pages show no
   rail.
4. Budget: create a campaign with serve budget 2 → its ad serves twice, then
   stops (admin card shows `2/2 serves`); blank budget shows `∞`.
5. Why-served log: `SELECT why_served, pincode, slot_key FROM ads.delivery_decisions`
   (sampled — set `ADS_DELIVERY_LOG_SAMPLE=1.0` in dev to see every serve;
   `local_pincode`/`global` values, viewer hash only, no user ids). UPDATE/DELETE
   on the table must fail (append-only).
6. Geo-context: `/api/ads/serve` ignores a client-forged `pincode` query param —
   the BFF overwrites it from the `agri_loc` cookie (change location via the pill
   → served local inventory follows).

## M4 — Automatic pincode tiers (:8000 + :3004/ops)

Every pincode gets a T1 (metro) .. T5 (extreme rural) tier from a percentile
classifier over census population, refined by verified-user counts once a
pincode has enough signups (`method` flips `population` → `population+users`).
Promote-only: the nightly job never demotes a pincode, only an admin override
can (and the next nightly run re-promotes it). TN is fully covered; pan-India
rows load dormant (no serving effect yet — design decision, not a bug).

1. Load + classify (from `backend/core`, venv python):
   `python -m scripts.load_pincode_tiers` — loads `data/geo/pincode_population.csv`
   and classifies every row in one idempotent command (NN1). Re-running with no
   data changes reports `0 changed`. A failed sanity check exits non-zero and
   commits nothing (bad-source-data threat).
2. `:3004/ops` (staff login) → "Pincode tiers" card: histogram bars T1..T5,
   pincode count per tier, and a method breakdown line (`population: N ·
   population+users: N`). Empty state (`📍 No pincode tiers loaded yet`) before
   step 1 has run; a non-staff/non-super_admin session sees the `🔒 restricted`
   card instead of the histogram (`GET /admin/ops/pincode-tiers/distribution`
   returns 403).
3. Nightly re-rank: `python -m scripts.geo_tier_nightly` — recounts verified
   users per pincode and reclassifies (promote-only + `tier_changed_at`
   hysteresis interval). `GEO_TIER_JOB_ENABLED=false` is the kill switch (no-op
   run, exit 0).
4. Admin override: `POST :8000/admin/ops/pincode-tiers/641001` with staff/
   super_admin auth and body `{"tier": 1}` → 200 with the new tier. Confirm:
   - `GET :8000/admin/ops/pincode-tiers/641001` now reports `tier: 1`.
   - `SELECT * FROM geo.pincode_tier_history WHERE pincode = '641001' ORDER BY
     created_at DESC LIMIT 1;` — one new row, `reason = 'admin_override'`,
     `old_tier`/`new_tier` populated (append-only history, NN4).
   - Staff audit log (`shared.audit`) has a fresh `geo.tier_override` entry for
     the acting admin with `meta = {"pincode": "641001", "tier": 1}`.
   - The `/ops` histogram (step 2) reflects the new bucket on next reload.
   - A bad tier (`{"tier": 9}`) → 422; an unmapped pincode → 404.
5. Delivery accessor sanity: pick a business whose coverage pincode was just
   overridden and confirm ad delivery keeps serving normally — the tier feeds
   `delivery_decisions` logging only (M3's `why_served` log), it never blocks
   or changes who is servable (no-delivery-blocking DO-NOT).

## M3 — Delivery blend + sponsored listings (merged)

1. Blend (NN#1): in `:3004/ads` make TWO campaigns for the advertiser — one with NO
   pincode targeting (global), one targeted to 641001 (local), same slot. At
   `/en/coimbatore/641001` both rotate into the slot (local ~2× more often); at a
   non-targeted pincode only the global one appears.
2. Sponsored listings: a `milk_sponsored_listing` placement injects the advertiser's
   card into category/covers/search lists — ONLY at positions 1 and 6, max 2 per
   page, always ★ Sponsored, and the organic result count/order is unchanged
   (compare the list with the campaign paused vs active — organic order identical,
   NN#3).
3. Per-category independence (NN#2): a campaign targeted to category `ghee` never
   appears on the paneer page/chips.
4. "Recommended" is organic-only: the Recommended rail ranks by
   verified+rating+response-time — a paying advertiser's card in the same list
   carries ★ Sponsored, never "Recommended" (NN#4 / labeling law).
5. Delivery log: every serve lands a why-served row —
   `docker exec agri-dev-postgres-1 psql -U app -d agri -c
   "SELECT slot_key, pincode, reason FROM ads.delivery_decisions ORDER BY occurred_at DESC LIMIT 5;"`
   (hashed session only, no user ids).

## M4 — Automatic pincode tiers (IN PROGRESS on feat/m4-pincode-tiers)

Built so far: census population snapshot, `geo.pincode_tiers` (+ append-only history),
population loader, percentile classifier + `scripts/load_pincode_tiers.py`.
Still landing: user-count re-rank hook, Ops-console histogram view.

1. Load + classify: from `backend/core`,
   `.venv/Scripts/python.exe scripts/load_pincode_tiers.py` → then
   `psql ... -c "SELECT tier, count(*) FROM geo.pincode_tiers GROUP BY tier ORDER BY tier;"`
   — T1≈top-1% metros … T5 extreme rural; thresholds come from settings, not code.
2. Idempotent: run the loader twice → same counts, NO new rows in the tier history
   table (history rows appear only when a tier actually changes).
3. Spot checks: 641001 (urban Coimbatore) lands T1/T2; a remote village pincode
   lands T4/T5. TN coverage complete; pan-India rows load but stay dormant.
4. (After the remaining tasks land) `:3004` ops view shows the tier distribution
   histogram; user-count promotions never auto-demote.

## M5 — Advertiser self-serve ads + billing (:3002/business/ads + :3004/ops, this branch)

Advertisers build and pay for their own campaigns (banner CPM or
`*_sponsored_listing` flat-weekly) instead of Ops creating them by hand. A
campaign only reaches `active` once BOTH payment (ad-order paid) AND
creative moderation (approved) have landed (`modules/ads/lifecycle.py`) —
either alone leaves it stuck in `pending_payment`/`pending_moderation`.

This walk uses **real Razorpay TEST mode**, not the e2e stub: set
`RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/`RAZORPAY_WEBHOOK_SECRET` to TEST
credentials, leave `RAZORPAY_TEST_STUB=false`, and point a TEST-mode
webhook at your reachable dev/staging origin (`ngrok`/similar) subscribed to
`payment_link.paid`, `payment_link.expired`, `refund.processed` (see
`docs/runbooks/billing-flag-flip.md`'s M5 section for the full dashboard
checklist). Flip both `ads_enabled` and `billing_enabled` on via
`:3004/ops` → Flags (or `/admin/ops/flags`).

1. Wizard, phone-sized viewport (DevTools device toolbar, ~375px wide):
   `:3002/business/ads` as a vendor owner → "New campaign". Walk all six
   steps (Goal → Categories → Areas → Schedule & budget → Creatives →
   Review & pay) — the quote rail re-prices live as you change categories/
   areas/serves, every control stays reachable/44px+ at phone width, no
   horizontal scroll.
2. Pay: "Review & pay" hands off to a Razorpay-hosted Payment Link
   (`checkout_url`/`razorpay_short_url` from `POST /billing/ad-orders`).
   Use a [Razorpay TEST card](https://razorpay.com/docs/payments/payments/test-card-upi-details/)
   to complete checkout. You land back on `/business/ads?paid={campaign_id}`
   (the Payment Link's `callback_url`).
3. Webhook activation: confirm the `payment_link.paid` webhook actually
   fired (Razorpay dashboard → webhook logs, 200 response) and the order
   flipped `created` → `paid` — `GET /billing/ad-orders?campaign_id=...`
   from the console, or `psql` `billing.ad_orders`/`billing.ledger_entries`
   (one `ad_charge` row, amount matches the quote exactly). Campaign stays
   `pending_moderation` at this point if the creative isn't approved yet.
4. Ops approve the creative: `:3004/ops` (or `:3004/ads`) → moderation
   queue (`GET /admin/moderation/queue?type=creative`) → approve
   (`POST /admin/moderation/creative/{id}/approve`). With payment already
   captured, approval flips the campaign to `active`
   (`campaign.activated` notify event).
5. Targeted serve: confirm the ad serves at the campaign's targeted
   pincode × category (and NOT at an untargeted pincode or a different
   category) — same check as the M3 walk above (`ads.delivery_decisions`
   log), just via a self-serve campaign instead of an Ops-created one.
6. Invoice: confirm the advertiser's account/inbox got the invoice email
   with the GST invoice PDF attached (`billing.ad_invoice` notify event,
   sent from the billing worker's invoice-PDF sweep — the worker must be
   running for this step to fire; see the runbook). Cross-check
   `GET /billing/ad-invoices/{invoice_id}/pdf` downloads the same PDF.
7. Refund → pause: from the Razorpay TEST dashboard, issue a full refund
   against the captured payment. Confirm `refund.processed` lands
   (webhook logs), the ledger gets a matching `ad_refund` entry
   (`billing.ledger_entries`), the order flips to `refunded`, and the
   campaign pauses (budget zeroed, drops out of delivery) — a **partial**
   refund must NOT pause a still-serving campaign, so if you test that case
   separately confirm the campaign keeps serving.
8. Rate card v2: `:3004/ads` → rate-card panel (`RateCardPanel`, or
   `POST /admin/ads/rate-card` directly, staff/super_admin) → publish a new
   config
   (bump a `cpm_paise`/`flat_weekly_paise`/`category_multipliers_bp`
   value). Confirm `GET /admin/ads/rate-card` now reports the new version,
   and a fresh wizard quote (`POST /ads/my/quote`) on step 1-4 reflects the
   new numbers — an already-priced draft campaign keeps its OLD snapshot
   until re-quoted (pricing is snapshotted at quote time, never re-derived
   at checkout).

Known caveat to confirm during this QA pass, not assumed: the Payment
Link's expiry (`LINK_EXPIRY` in `modules/billing/ad_orders.py`) is a
hardcoded 24h. We currently assume an unexpired-but-since-paid link still
emits `payment_link.paid` (not `payment_link.expired`) — worth confirming
against Razorpay's own docs/behavior during this walk rather than taking it
on faith, since `apply_payment_link_paid` does tolerate a late paid event on
an `expired` local order (races on Razorpay's side), but the reverse
(`payment_link.expired` arriving after a real payment already landed) is
not something we've observed directly against a live TEST account.

## Known-open items (do not file as new bugs)

- ~~Landing perf CI floor temporarily 0.80 (issue #45)~~ — RESOLVED: PR #48 (inline
  CSS + Devanagari SVG) restored the 0.90 gate; it must stay at 0.90.
- Real-device push confirmation is owner-run hardware work (checklist above).

---

*Perf tracking moved from #42 to [#45](https://github.com/oneuni-in/agri-ecosystem/issues/45): the original issue was deleted, and #45 carries the accumulated findings forward.*
