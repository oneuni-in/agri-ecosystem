# MILK.IN BUILD PACK — D23–D32: FIRST LAUNCH 🥛
# Aligned to v5 MASTER Block 4. One spec per fresh session · branch off dev → PR → dev → merge same day.
# Prereq: v0.3.0 tagged (shared engines done). Geo is TN-scoped (geo-all-india skipped) — non-TN pincodes
# show a graceful "not covered yet" state, NOT an error.
# ENDS AT: D32 — merge dev→main, tag v1.0.0-milk, DNS cutover, first live platform.
#
# ⚠ CRITICAL EXTERNAL CLOCK: DLT SMS registration. D30 requires REAL SMS working. If DLT is unfiled/
#   unapproved by D30, either (a) delay launch until it clears, or (b) launch with mock-OTP DISABLED and
#   a "login coming shortly" hold — do NOT launch real signup on a mock driver. Verify DLT status NOW.
#
# STANDING RULES (carried from D13/D14/Sprint-2, apply every spec):
#   • git status zero AM before every commit · committed-tree verify after conflict resolution.
#   • Migration number next in committed chain · filename == internal revision.
#   • app_rt = least privilege; loaders/admin use app. · Header widgets extend AuthCluster, never duplicate.
#   • Coins/notify/search interactions go via EVENTS + service boundaries, never cross-module imports.
#   • Milk.in is CONFIGURATION over the Sprint-2 engines (directory/coverage/products/reviews/leads/
#     search/ads) — reuse, don't rebuild. New code only where milk-specific.

═══════════════════════════════════════════════════════════════
## SPEC D23 — PINCODE-FIRST HOME + EMPTY-STATE CONTRACT (~6.5h) · feat/d23-milk-home
═══════════════════════════════════════════════════════════════
CONTEXT: Milk.in's homepage IS a pincode box (per mockup). Enter pincode → every milk option nearby.
Built on D15 covers() + D19 location context + D17 milk products. web-milk app, theme-milk, design-system.md.

DO:
A. Pincode-first hero (ISR): big PincodeInput (design-system component) + GPS fallback ("use my location").
   On submit → covers(pincode) → blended results: brands + local vendors, milk-type filters, price banner.
B. **Three-way empty-state contract** (the graceful handling):
   (a) valid TN pincode + vendors → results;
   (b) valid TN pincode + zero coverage → warm "No milk vendors in {district} ({pincode}) yet — notify me
       / list your dairy" (captures demand — feeds seeding priority; NOT an error);
   (c) non-TN or invalid pincode → honest "We're live in Tamil Nadu right now — {other areas} coming soon"
       + notify-me. (Because geo is TN-scoped; this is by design, styled warm, never a crash.)
C. Milk-type filter row (TypeFilterRow component): All/Cow/Buffalo/A2/Organic/Curd&Ghee/Home-delivery —
   filters the milk-vertical products (D17 schema); horizontally scrollable, icon+vernacular.
D. Today's price-range banner: computed from listed products' price_display in that pincode
   ("Cow ₹52–60/L · Buffalo ₹68–75/L · N sellers found").
E. Location context wired (D19): resolved pincode persists to profile; header LocationPill switches it.
F. SEO: home + pincode routes SSR/ISR, JSON-LD, sitemap entries (pincode landing detail lands D28).

INTEGRATION SURFACE: reuses covers() (D15) + location context (D19) + products (D17) — confirm the
milk-type filters read the D17 milk spec-schema (type/fat/pack), not hardcoded. No new migration expected
(uses existing tables); if any, chain-verify. Empty-state (b) "notify me" writes a lead/interest record
(reuse D18 leads or a lightweight interest capture) — pick one, don't fork.

DO NOT: no vendor profiles yet (D24) · no need-posting yet (D25) · no hardcoded milk types (schema-driven) ·
empty states are warm features, never error screens · no offset paging on results.
NON-NEGOTIABLES: 1. all three empty-state branches render correctly (tests: 641001 w/ seed vendor,
641xxx w/ none, 110001 non-TN) · 2. milk-type filters driven by D17 schema · 3. home is ISR/SSR + JSON-LD +
Lighthouse ≥90 · 4. price banner computes from real listings.
THREAT MODEL: pincode enumeration for scraping (rate-limit covers()); empty-state as info leak (only
public directory data shown).
DoD: three empty-state tests green; Lighthouse ≥90; PR → dev. `feat(d23): milk pincode home`.

═══════════════════════════════════════════════════════════════
## SPEC D24 — VENDOR PROFILES + TRACKED CONTACT + MAP (~6.5h) · feat/d24-vendor-profiles
═══════════════════════════════════════════════════════════════
CONTEXT: Vendor/brand detail pages with tracked Call/WhatsApp/form + a map/list view. Built on directory
(D15) + reviews (D18) + leads (D18 contact-reveal). LocalBusiness JSON-LD for SEO.

DO:
A. Vendor/brand profile page (SSR, slug URL): products (D17 milk schema), coverage pincodes, delivery
   windows, price display, reviews (D18 login-gated), verification badge (D16). LocalBusiness JSON-LD.
B. **Tracked contact buttons** (design-system CallButton/WhatsAppButton): Call/WhatsApp reveal goes
   through D18 contact-reveal caps (login-gated + daily cap + logged, no plaintext phone in logs); the
   reveal + a lead "contact" inquiry are recorded (attribution for the vendor's response stats).
C. Form fallback: "request contact" lead (D18) for guests / when user prefers not to call.
D. Map + list sync (MapLibre): vendors plotted by branch centroid, list ↔ map selection synced,
   distance-sorted. Mobile map perf tuned (cluster if many).
E. Reviews section: read + login-gated write (D18), moderation-pending default.

INTEGRATION SURFACE: contact reveal MUST use D18's cap + reveal-log (don't reimplement) — verify plaintext
phone never logged. Map uses branch lat/lng from D15. Review write emits review.approved→coins (D18 event),
cap 5/week. No new PII surface beyond the audited reveal path.
DO NOT: no un-capped contact reveal · reviews never auto-publish · no phone in logs/URLs · MapLibre only
(no Google Maps JS for the map itself; Maps key is for locator geocoding if needed later).
NON-NEGOTIABLES: 1. contact reveal capped + logged w/o plaintext phone (test) · 2. LocalBusiness JSON-LD
validates · 3. map↔list selection synced (test) · 4. profile SSR + Lighthouse ≥90.
THREAT MODEL: contact scraping via profile pages (reveal caps), review brigading (D18 guards), map data
scraping (rate limit).
DoD: reveal-cap + JSON-LD + map-sync tests green; PR → dev. `feat(d24): vendor profiles`.

═══════════════════════════════════════════════════════════════
## SPEC D25 — "POST MY NEED" SUBSCRIPTION-INTENT LEADS (~6.5h) · feat/d25-post-need
═══════════════════════════════════════════════════════════════
CONTEXT: The killer flow — user posts "1L cow milk daily in 641001", covering vendors get it, respond,
user notified. Built on D18 leads (milk_subscription type) + coverage routing. Icon-first, speakable shell.

DO:
A. "Post my need" flow (icon-first, low-literacy friendly per design system): quantity, milk type
   (from D17 schema), pincode (prefilled from location), schedule (daily/alternate/weekly), delivery time
   preference. Voice-note capture SHELL (stored; transcription is Phase 2 — the icon+field form fully works
   for all users now).
B. Routing: milk_subscription inquiry (D18) → covers(pincode) matching vendors → each vendor's inbox →
   vendor responds → user notified (D12). Both-side status tracking (new/responded/closed).
C. User "my needs" view: posted needs + responses received + accept/mark-fulfilled.
D. Guest-friendly: can post with just phone+OTP (D07) — becomes a progressive account (D11).

INTEGRATION SURFACE: uses D18 leads engine (milk_subscription type) + covers() routing + D12 notify.
Confirm routing only hits vendors covering the pincode (reuse, don't rebuild the matcher). Voice-note blob
uses the D17 media pipeline (presign/re-encode) — audio type allowed, size-capped. Guest→account uses D07/
D11 progressive flow.
DO NOT: no payment (pure intent routing) · no transcription now (shell only) · no routing to non-covering
vendors · no offset paging.
NON-NEGOTIABLES: 1. need routes only to covering vendors (641001 test) · 2. both-side status tracked ·
3. guest can post via OTP → progressive account · 4. voice shell stores blob safely (type/size validated).
THREAT MODEL: spam needs (rate-limit + phone-verify), vendor inbox flooding (per-user caps), voice-blob
abuse (type/size/scan).
DoD: post→route→respond→notify E2E green; PR → dev. `feat(d25): post my need`.

═══════════════════════════════════════════════════════════════
## SPEC D26 — VENDOR DASHBOARD (~6h) · feat/d26-vendor-dashboard
═══════════════════════════════════════════════════════════════
CONTEXT: Where vendors manage everything. Built on the Business Console shell (D20) + directory/products/
leads. Premium tier ties to billing (flagged) + priority sort.

DO:
A. Vendor dashboard (Business Console mount): manage listing (D15), coverage pincodes editor, products
   (D17 schema-driven forms), delivery windows/timings.
B. Lead inbox: incoming needs (D25) + contact leads (D24), respond, mark status; response-time stats
   surfaced (nudge slow responders).
C. Premium tier: subscribe (D20 billing, flag-gated) → priority placement (wired to result sort in D23/
   D24). While billing flag off: tier selectable but "activate at launch" state; sort respects tier field.
D. Analytics-lite: profile views, contact reveals, leads received (from tracking) — by pincode.

INTEGRATION SURFACE: mounts into D20 Business Console (extend, don't fork the shell). Premium sort reads a
tier field usable even while billing is dark. Coverage editor writes to D15 business_coverage. Confirm
owner-scoped (owned_by) everywhere — a vendor edits only their own.
DO NOT: no billing charges while flag off (tier is selectable, activation deferred) · no cross-vendor
data access (IDOR) · no offset paging.
NON-NEGOTIABLES: 1. all vendor writes owner-scoped (IDOR test) · 2. premium sort works with tier field
pre-billing · 3. response-time stat accurate · 4. coverage editor updates covers() results.
THREAT MODEL: cross-vendor IDOR (owned_by), fake premium via tier tampering (server-set only, never client).
DoD: owner-scoped + premium-sort + coverage-edit tests green; PR → dev. `feat(d26): vendor dashboard`.

═══════════════════════════════════════════════════════════════
## SPEC D27 — DAIRY DIRECTORY + BRAND PAGES + SEED (~5.5h) · feat/d27-dairy-directory
═══════════════════════════════════════════════════════════════
CONTEXT: Mount the adjacent dairy categories (config, reuses directory) + brand "shops near you" pages.
[BG] the real seed: 150+ Coimbatore-region vendors/brands + TA/HI strings.

DO:
A. Dairy directory categories via registry (D17) — vets, feed suppliers, dairy farms, cooperatives —
   pure config on the directory engine; category landing + covers()-based browse.
B. Brand pages (Aavin/Hatsun/Sakthi-style): products + "shops near you" computed from branch data (D15);
   nearest-shops list by pincode.
C. [BG] SEED (the launch-critical data): 150+ Coimbatore vendors/brands normalized (from D19's prepared
   CSVs) → bulk import (D63's pipeline isn't built yet, so a careful D27 import script) → review → load.
   TA/HI translations for all Milk.in UI strings + seeded content (glossary-consistent).
D. Verify cross-links: dairy service categories appear from vendor pages.

INTEGRATION SURFACE: categories are config on directory (no new engine). Seed import writes businesses +
branches + coverage + products — run as `app` (admin role), validate against schemas, dedupe. Confirm
seeded vendors appear in covers(641001) AND in search (D19 indexer picks them up via events — verify they
actually get indexed, the classic stale-index seam).
DO NOT: no new engine (config only) · no unvalidated seed rows · no thin nationwide seeding (Coimbatore
depth only) · seeded content still moderation-appropriate.
NON-NEGOTIABLES: 1. seeded vendors appear in covers(641001) + search (index test) · 2. TA/HI strings
complete (locale completeness check) · 3. brand "shops near you" accurate by pincode · 4. import idempotent.
THREAT MODEL: bad seed data eroding trust (validation + review), duplicate listings (dedupe on import).
DoD: seed loaded + searchable + covers() test green; 3-locale complete; PR → dev. `feat(d27): dairy directory + seed`.

═══════════════════════════════════════════════════════════════
## SPEC D28 — PWA + PINCODE SEO PAGES (~6h) · feat/d28-pwa-seo
═══════════════════════════════════════════════════════════════
CONTEXT: Make Milk.in installable + offline-capable (rural reality) and generate the SEO pincode landing
pages. Built on the D02 PWA/SEO primitives.

DO:
A. PWA: manifest (theme-milk, icon, splash), service worker, **offline shell** (last-seen prices +
   helpline numbers cached), install prompt, web push (D12 → push channel for lead/response alerts).
   iOS web-push (16.4+) + Android.
B. **Pincode landing pages** (ISR): milk.in/{city}/{pincode} — SSR, LocalBusiness/ItemList JSON-LD,
   noindex-until-populated (self-noindex if zero vendors, per D02 shouldNoIndex), auto-sitemap entries.
C. Low-data mode: image quality toggle, lazy loading (rural bandwidth).
D. Canonical + redirect hygiene (immutable slugs, 301s from D03).

INTEGRATION SURFACE: PWA push extends D12 notify (new push channel, preferences respected). Pincode pages
read covers() — thin (zero-vendor) pincodes self-noindex (no thin-content penalty). Sitemap auto-generates.
DO NOT: no indexing thin pages · no PII in cached offline shell · no blocking JS on first paint (Lighthouse).
NON-NEGOTIABLES: 1. installable PWA (Android+iOS) w/ offline shell (test) · 2. thin pincode pages
noindexed, populated ones indexed + JSON-LD valid · 3. low-data mode works · 4. Lighthouse ≥90.
THREAT MODEL: cached PII in SW (cache only public data), push abuse (preference-gated).
DoD: PWA install + offline + noindex + Lighthouse tests green; PR → dev. `feat(d28): pwa + seo`.

═══════════════════════════════════════════════════════════════
## SPEC D29 — FULL QA + DEVICE MATRIX (~6h) · feat/d29-milk-qa
═══════════════════════════════════════════════════════════════
CONTEXT: End-to-end journeys + real-device reality. No new features — prove the product works for every user.

DO:
A. E2E (Playwright): discover→call (tracked), post-need→vendor-respond, subscribe-tier (flag-aware),
   claim→verify (D16), review round-trip, all three empty states.
B. Device matrix: low-end Android (Chrome), iOS Safari, desktop — layout, tap targets, PWA install,
   map perf. Document results.
C. Vernacular pass: every screen in EN/TA/HI, no layout breaks, CategoryTile/filters in Tamil.
D. Low-data + slow-network pass (throttled 3G): usable, images degrade gracefully.
E. Accessibility sweep: focus rings, screen-reader labels on Call/WhatsApp/filters.

INTEGRATION SURFACE: exercises every prior Milk.in spec + shared engines together — this is the
integration test the individual specs couldn't do alone (the D13 lesson: seams surface only in combined runs).
DO NOT: no new features · don't paper over a real bug with a skipped test.
NON-NEGOTIABLES: 1. all core journeys green on the matrix · 2. 3-locale no-break · 3. throttled-3G usable ·
4. a11y labels present.
DoD: matrix documented, journeys green; PR → dev. `feat(d29): milk qa`.

═══════════════════════════════════════════════════════════════
## SPEC D30 — SECURITY FREEZE + DLT VERIFY (~6h) · feat/d30-milk-security
═══════════════════════════════════════════════════════════════
CONTEXT: Adversarial audit of the whole Milk.in surface + production edge config. ⚠ DLT day — real SMS
must work or the launch decision changes.

DO:
A. Adversarial audit (fresh session → docs/security/milk-audit.md): full Milk.in surface + auth + leads
   contact-reveal + vendor dashboard IDOR + seed-data + PWA cache + OWASP checklist. Fix Critical/High.
B. **DLT / real SMS verification:** switch sms_provider=msg91, send a real OTP end-to-end, confirm
   delivery + template compliance. If DLT NOT approved: STOP and decide — delay launch, or launch with
   signup gated ("login coming shortly"). Do NOT launch real signup on the mock driver. Record the decision.
C. Cloudflare production config: WAF managed rules, bot fight, rate limits on /auth/* + covers() +
   contact-reveal, country challenge if needed.
D. Load test (k6): 500 concurrent browse / 50 concurrent auth — p95 within budget.
E. [YOU] fix triage — every High closed before launch prep.

INTEGRATION SURFACE: this is the pre-launch seam sweep — committed-tree verify, app_rt grants, public_routes
hand-review, one-of-each header widgets. milk-audit.md committed.
DO NOT: no launch on mock OTP · no unclosed High findings · no gate soft-disable.
NON-NEGOTIABLES: 1. zero Critical/High at freeze · 2. real SMS verified OR launch-gate decision recorded ·
3. WAF + rate limits live · 4. k6 within budget.
THREAT MODEL: this day is the threat model — plus the DLT go/no-go.
DoD: milk-audit.md complete, SMS decision recorded, k6 pass; PR → dev. `feat(d30): milk security freeze`.

═══════════════════════════════════════════════════════════════
## SPEC D31 — LAUNCH PREP (~6h) · feat/d31-launch-prep
═══════════════════════════════════════════════════════════════
CONTEXT: Everything non-code that a launch needs. VPS is provisioned NOW (it was deferred — this is when
you need it). Deploy dry-run, legal, backups, on-call.

DO:
A. **VPS + production infra** (deferred until now): provision, harden (SSH keys, ufw), Docker,
   docker-compose.prod, Caddy/Nginx TLS, R2 live, Sentry prod, Uptime Kuma prod. Wire the D04 staging→prod
   deploy path (from main). DNS ready on Cloudflare (domains already there).
B. Deploy dry-run to production infra from a release candidate; smoke test; **rollback rehearsal**.
C. Legal pages LIVE: privacy, terms (lead-gen disclaimers — platform is not the seller), AgriCoins T&C.
   DPDP: consent capture + data export + delete endpoints verified working.
D. **Restore drill #2** against production backups (real, timed). On-call checklist. Support inbox (you).
E. Final content seed check; monitors + alerts armed.

INTEGRATION SURFACE: first real production deploy — verify secrets (SOPS) present, app_rt vs app roles set
correctly in prod env (the D13 env-split lesson), billing_enabled=false confirmed in prod, DLT/msg91 keys
present if launching real signup.
DO NOT: no launch without a rehearsed rollback · no missing legal/DPDP · no prod secret in code.
NON-NEGOTIABLES: 1. deploy dry-run + rollback rehearsed · 2. restore drill #2 executed + timed ·
3. legal + DPDP live and verified · 4. prod env roles/secrets/flags correct.
DoD: dry-run + rollback + restore drill done; legal live; PR → dev. `feat(d31): launch prep`.

═══════════════════════════════════════════════════════════════
## SPEC D32 — 🥛 MILK.IN LAUNCH (~day) · feat/d32-launch → promote v1.0.0-milk
═══════════════════════════════════════════════════════════════
CONTEXT: First live platform. Promote, cut over, watch.

DO:
A. Final pre-launch checklist (v5 Part 5): security audit clean · SEO (JSON-LD, sitemaps, thin noindexed) ·
   legal/DPDP · quality (matrix, vernacular, low-data) · ops (monitors, on-call, hotfix lane) · data (seed +
   TA/HI complete) · DLT/SMS status confirmed.
B. **Promote:** PR dev→main (human review) → merge → `git tag v1.0.0-milk && git push origin v1.0.0-milk`.
C. Deploy main to production; DNS cutover on Cloudflare; smoke tests green; monitors watched.
D. Launch-day watch: Sentry + Uptime + first-user funnel; hotfix lane open all day.
E. [BG] OrganicStore.in specs finalized for D33.

INTEGRATION SURFACE: the real cutover — confirm prod == the tested main tree; SMS live (or signup-gate
active); billing dark; backups running; rollback ready.
DO NOT: no launch with any open High · no unrehearsed cutover · no signup on mock OTP.
NON-NEGOTIABLES: 1. full launch checklist green · 2. v1.0.0-milk tagged from main · 3. monitors + hotfix
lane live · 4. rollback one command away.
DoD: Milk.in live, monitored, stable. → request the OrganicStore.in pack (D33–D44).

───────────────────────────────────────────────────────────────
⚠ THE ONE THING THAT CAN STOP D32: DLT. It's been on hold. Real signup needs approved DLT SMS. Check
status TODAY (you're ~9 build-days out). If it won't clear by D30, the fallback is a signup-gated soft
launch (browse works, "login coming shortly"), then flip signup on when DLT clears — but decide
deliberately at D30, not by surprise at D32.
