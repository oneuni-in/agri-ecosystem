# Manual UI test guide — D23 → D29 (milk.in sprint 3)

Owner-facing walkthrough for hand-testing everything shipped in D23–D29 on a dev box.
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
`scripts/import_vendor_seed.py` (150+ Coimbatore vendors/brands; idempotent; `--dry-run` first).

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

## Known-open items (do not file as new bugs)

- Landing perf CI floor temporarily 0.80 (issue #42) — must return to 0.90 by D32.
- Real-device push confirmation is owner-run hardware work (checklist above).
