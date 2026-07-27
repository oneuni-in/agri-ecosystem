# D28 — PWA + Pincode SEO Pages — Design

Date: 2026-07-27 · Branch: `feat/d28-pwa-seo` · Spec: `docs/Sprint/sprint3_D23-D32.md` (D28)

## Context

Make Milk.in installable + offline-capable and generate SEO pincode landing pages, on the
D02 SEO primitives, the D23 milk-home blend endpoint, and the D12 notify engine. No PWA
machinery exists anywhere in the repo today (no `public/` dir, no manifest, no SW, no push
deps, no helpline data). The notify channel enum is `in_app|sms|email`.

## B. Pincode landing pages — `/{city}/{pincode}`

**Forced move:** Next.js App Router forbids two different slug names at the same path
position, so `app/[locale]/[city]/[pincode]` cannot coexist with the existing
`app/[locale]/[pincode]`. The existing pincode page therefore MOVES:

- `app/[locale]/[pincode]/` → `app/[locale]/[city]/[pincode]/`. Same page (3-way scope,
  type filters, `?category=` browse, ItemList-of-LocalBusiness JSON-LD, `noIndex:
  !covered`), now with: canonical `/{city}/{pincode}`, hreflang (en/ta/hi/x-default,
  D27 pattern — metadata is the single hreflang source, `alternateLinks: false` stays),
  and city-slug validation — `slugify(district) !== city` → `permanentRedirect` to the
  correct URL (kills duplicate-content variants).
- New `app/[locale]/[city]/page.tsx`:
  - param matches `^\d{6}$` → fetch milk-home; district resolves → **301**
    (`permanentRedirect`) to `/{district-slug}/{pincode}` preserving query; out-of-area
    (no district) → render the existing out-of-area UX in place, noindex; backend
    unreachable → `notFound()` (matches current behavior).
  - anything else (bare city slug) → `notFound()`. No city landing page (YAGNI).
- Internal links: server-rendered links (TypeFilterRow, CategoryChips, filtered-empty
  "see all", vendor/brand cards, category results) build `/{city}/{pincode}` directly
  from the district the page already has. `pincode-hero` keeps navigating to
  `/{pincode}` (it has no district yet) and eats one 301 after user action —
  acceptable, not an SEO surface.
- City slug = slugified `geo.districts.name` ("The Nilgiris" → `the-nilgiris`).
  Single TS implementation in `packages/ui` (`citySlug()`), unit-tested. The backend
  never produces slugs — the coverage endpoint returns raw district names.

**Sitemap:** new public endpoint `GET /directory/coverage/pincodes?cursor=&limit=`
(SecureRouter `public=True`, keyset on pincode, limit ≤100) → `{items: [{pincode,
district}], next_cursor}`. Criterion = the SAME "covered" predicate as milk-home
(≥1 active, non-deleted covering business with an approved+active milk product) —
anything looser would put self-noindexing pages in the sitemap. Added to
`public_routes.txt` with rationale. `app/sitemap.ts` walks all pages at ISR time,
emits `/{city}/{pincode}` entries, keeps `/` + `/c/{category}`, and falls back to just
those static entries (home + categories, no pincodes) if the backend is unreachable
(CI builds have no backend). The hard-coded `LAUNCH_PINCODES` stub is deleted. New
`app/robots.ts` (allow all, sitemap URL).

**Lighthouse:** the CI lighthouse job runs with NO backend (ci.yml — pnpm only), so the
landing URL cannot be CI-audited; the gate keeps auditing web-milk home. Landing-page
scores verified locally via the D04 recipe (Chrome :9222 + lighthouse core). This is a
structural constraint, not a carve-out request.

## A. PWA — hand-rolled SW, static manifest, zero new frontend deps

- **Manifest** `apps/web-milk/public/manifest.webmanifest` (static JSON — `check:hex`
  scans only `.ts/.tsx/.css`, so theme hex is legal there): name Milk.in, `display:
  standalone`, `start_url: /`, theme `#2563A8` (--brand, theme-milk), background
  `#F7F8F3` (--paper), icons 192/512 + maskable 512.
- **TS-side theme colors** (`generateViewport.themeColor`) come from a new
  `packages/config/theme-colors.js` export — packages/config is the hex-legal package;
  apps import tokens, never literals.
- **Icons**: `scripts/generate-pwa-icons.mjs` (repo-root scripts/, sharp — already an
  allowed build) renders an inline milk-glyph SVG → committed PNGs (192, 512,
  maskable-512, apple-touch-180). Android splash derives from manifest
  background_color+icon; iOS splash-image matrix (~20 PNGs) deliberately skipped —
  icon + status-bar meta only.
- **Service worker** `public/sw.js`, hand-rolled (~150 lines; next-pwa/serwist rejected:
  new deps, allowBuilds risk, less control over the no-PII cache rule):
  - versioned caches; precache `/offline` + manifest + icons on install.
  - fetch: same-origin GET only. Navigations → network-first, offline fallback to
    `/offline`. `_next/static/*` (content-hashed) → cache-first. **`/api/*` never
    intercepted, never cached** (threat model: no PII in SW cache).
  - `push` event → `showNotification(title, body)`; `notificationclick` → focus/open
    `/notifications`.
- **Registration**: client island in `[locale]/layout.tsx`; registers when
  `NODE_ENV === "production"` or `NEXT_PUBLIC_ENABLE_SW=1` (e2e escape hatch).
- **Offline shell** `app/[locale]/offline/page.tsx` (static segment beats `[city]`
  sibling): helpline numbers + last-seen prices. Prices: the pincode page writes
  `{pincode, district, lines, ts}` (public price-banner data only) to `localStorage`
  client-side; the offline page reads it. Helplines introduced by D28 as i18n messages
  (en/ta/hi): Animal Husbandry helpline **1962**, Kisan Call Centre **1800-180-1551**.
  Page is noindex.
- **Install prompt**: client island — Android/Chrome `beforeinstallprompt` → deferred
  custom banner; iOS Safari (no event) → "Add to Home Screen" hint when not standalone
  and iOS≥16.4-capable; dismissal persisted in a cookie (~30d).

## A2. Web push — D12 notify gains a `push` channel

- **Migration 0027** (THREAT/NOTES filled):
  - `ALTER TYPE notify.notify_channel ADD VALUE IF NOT EXISTS 'push'` inside
    `op.get_context().autocommit_block()` (first enum extension in the repo; new value
    unusable in the adding transaction on PG16). Downgrade cannot remove an enum value
    — documented, harmless (IF NOT EXISTS keeps migrate_check green).
  - `notify.push_subscription`: UUIDv7 PK, timestamps, `user_id` (indexed),
    `endpoint` TEXT UNIQUE, `p256dh` TEXT, `auth` TEXT, `ua_label` TEXT NULL.
    Hard-delete on unsubscribe and on 404/410 push responses (no soft-delete —
    a dead subscription has no audit value). Explicit per-table GRANT for `app_rt`
    (0023/0025 precedent, never blanket).
  - Seed push templates `lead_received`/`lead_response` × en/ta/hi (`subject` column
    reused as push title — the model has no separate title field);
    `tests/test_notify_templates.py::EXPECTED_CHANNELS` updated in the same PR.
  - Flag `notify.push_enabled` seeded **false** (mirrors `email_enabled`; flips when
    VAPID keys are provisioned).
- **Dispatch** (`modules/notify/service.py`): channel allowlist `{"sms","email"}` →
  `{"sms","email","push"}`. Push branch rides the existing pipeline: preference
  (`channel_enabled`) → flag (`push_enabled`) → subscriptions lookup by user_id
  (none → `NOTIFY_DROPPED("no_destination")`) → one `Delivery` per subscription
  (`destination` = endpoint URL — same never-log class as email destinations) →
  `_attempt` push branch. Existing retry/backoff machinery applies unchanged.
- **Driver** `WebPushDriver` in `modules/notify/drivers.py` (import-linter contract
  keeps drivers notify-private): **pywebpush** (new backend dep; sync → wrapped in
  `asyncio.to_thread`), VAPID keys via `settings.vapid_public_key` /
  `vapid_private_key` / `vapid_subject` (empty default = kill switch). 404/410 →
  prune subscription row, delivery marked dead (no retry).
- **Events**: `EVENT_ROUTES` — `lead.created` and `lead.responded` gain
  `frozenset({"push"})`. Clean because push needs no destination in the event payload
  (module-independence preserved); review.approved stays in-app only (spec names
  lead/response alerts).
- **API**: `POST /notify/push/subscriptions` (upsert on endpoint) and
  `DELETE /notify/push/subscriptions` — both auth'd, private, rate-limited.
  `TOGGLEABLE_CHANNELS` + `PreferenceIn.channel` Literal gain `"push"`.
- **Frontend**: subscribe/unsubscribe card on web-milk `/notifications`
  (permission → `pushManager.subscribe` with `NEXT_PUBLIC_VAPID_PUBLIC_KEY` →
  POST via BFF). iOS: PushManager absent outside installed PWA → show install hint.
  Notify BFF proxy (`app/api/notify/[...path]/route.ts`) gains `PUT` + `DELETE`
  handlers (same path-traversal guard).

## C. Low-data mode

Cookie-backed toggle (`milk_lowdata`), site-footer client island, defaulting once from
`navigator.connection.saveData`. Wired effects: vendor map (~200KB MapLibre) not
auto-loaded when on — replaced by a "Load map" button; `loading="lazy"` on the
sponsored-ad `<img>`; `SmartImage` helper (lazy + decoding async + quality param for
media-domain URLs) for the images web-milk will render later. SSR reads the cookie so
the map island renders its placeholder without a client flash.

## D. Canonical + redirect hygiene

- `/{pincode}` → 301 → `/{city}/{pincode}` (above).
- Business slug renames: backend already 301s API fetches via SlugRedirectMiddleware
  (fetch follows transparently) but the page 404s on the stale URL. Fix: business page
  compares fetched `business.slug` to the URL param → `permanentRedirect` to the new
  slug. D03 `slug_redirects` finally surfaces on milk.in.
- Canonicals continue to strip query/hash (`canonicalUrl`); `?category=` views keep
  canonical `/{city}/{pincode}` + noindex (D27 rule).

## Testing (DoD mapping)

- e2e `pwa.spec.ts`: manifest served + valid (name/icons/display/start_url/theme);
  SW registers (env escape hatch); `context.setOffline(true)` → navigation falls back
  to offline shell showing helplines; last-seen prices render after visiting a covered
  pincode. Install-prompt banner logic unit-testable render (no real install event).
- e2e landing: `/641001` 301s to `/coimbatore/641001`; `/chennai/600001` (real geo:
  600001 = Chennai LGD 568) renders tn_no_vendors + robots noindex; `/coimbatore/641001`
  covered: no noindex, ItemList JSON-LD script present; wrong city 301s.
- Backend pytest: coverage endpoint (empty / seeded / cursor walk / active+approved
  predicate), subscription CRUD + auth, dispatch push (happy, no-subscription,
  preference-off, flag-off, 410-prune, retry-on-failure), template completeness
  (EXPECTED_CHANNELS), enum migration round-trip via migrate_check.
- Unit: `citySlug()` (packages/ui), meta/canonical additions.
- Gates: all 8 CI checks; `public_routes.txt` updated; no new frontend deps;
  backend gains `pywebpush` (pip-audit must stay green); Lighthouse home unchanged
  (SW registration + install-prompt islands are deferred, tiny).

## Owner veto points (flagged in PR)

1. URL restructure: `/{pincode}` now 301s to `/{city}/{pincode}`.
2. Helpline numbers chosen (1962, Kisan Call Centre 1800-180-1551).
3. New backend dependency `pywebpush`.
4. `push_enabled` stays false until owner provisions VAPID keys (generation command
   documented in the PR).
5. iOS splash-image matrix skipped.
