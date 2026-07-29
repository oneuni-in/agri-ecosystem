# D29 — Milk.in QA + Device Matrix

Branch `feat/d29-milk-qa` · Spec: `docs/Sprint/sprint3_D23-D32.md` (D29)

The DoD deliverable for D29.B. What was verified, on what, and — just as
important — what could **not** be verified in automation and therefore needs a
human with a real phone.

## 1. What runs where

Three Playwright projects share one set of dev servers
(`e2e/playwright.config.ts`):

| Project | Device | Scope | CI job |
|---|---|---|---|
| `desktop` | Desktop Chrome | every spec | `e2e-auth` |
| `mobile-chrome` | Pixel 5 (low-end Android proxy) | specs tagged `@matrix` | `e2e-matrix` |
| `mobile-safari` | iPhone 13 / WebKit | specs tagged `@matrix` | `e2e-matrix` |

Backend-shaped specs (`bff-path-traversal`, `sso`, `auth`) stay desktop-only —
nothing in them is device-dependent.

## 2. Journeys (spec D29.A)

Verified in CI, run
[30349985590](https://github.com/oneuni-in/agri-ecosystem/actions/runs/30349985590)
(2026-07-28, commit `4241fb1`), all 11 jobs green:

- `e2e-auth` (desktop, full suite): **75 passed**
- `e2e-matrix` (mobile-chrome + mobile-safari, `@matrix`): **81 passed, 5 skipped**

The 5 skips are all WebKit and all documented in §4: three signed-in journeys
(discover→call, the signed-in locale sweep, review round-trip) blocked by the
`Secure`-cookie limit, and two throttled-3G specs that need CDP. These figures
are from the CI run, not a local one.

| Journey | Spec | desktop | mobile-chrome | mobile-safari |
|---|---|---|---|---|
| discover → call, tracked | `discover-call.spec.ts` | pass | pass | **skipped** (§4.1) |
| post-need → vendor respond → fulfil | `post-need.spec.ts` | pass | n/a (desktop-only) | n/a |
| subscribe-tier, flag-aware | `vendor-dashboard.spec.ts` | pass | n/a | n/a |
| claim → verify (D16) | `claim-verify.spec.ts` | pass | n/a (§4.3) | n/a (§4.3) |
| review round-trip (D18) | `review.spec.ts` | pass | pass | **skipped** (§4.1) |
| three empty states (D23) | `milk-home.spec.ts` | pass | n/a | n/a |
| map ↔ list sync (D24) | `map-sync.spec.ts` | pass | n/a | n/a |
| pincode landing + PWA (D28) | `pincode-landing`, `pwa` | pass | n/a | n/a |

**Subscribe-tier is flag-aware, not flag-toggling.** `billing_enabled` is off
and stays off through launch, so the live branch is premium *intent*, and the
suite additionally asserts the server gate holds: `/billing/subscription` and
`/billing/invoices` return **404, deliberately not 403** — an unlaunched
product is invisible, not merely refused. There is no flag-ON e2e branch:
without a flag-set endpoint that means a DB write plus defeating the flag
cache, and D20 already covers the enabled path at the API level.

## 3. Screens (specs D29.C, D29.E)

Swept on all three projects: home, pincode landing, category, search,
post-need, offline, vendor profile — plus my-needs and notifications behind a
single login.

| Check | Result |
|---|---|
| Layout holds in EN/TA/HI (no horizontal overflow, 360px) | pass, 21 route×locale combinations |
| No untranslated `ui.*` keys leak as visible text | pass |
| Type filters render Tamil under `/ta` | pass |
| `/hi` applies Devanagari | pass |
| Locale switcher preserves the current route | pass |
| Tap targets ≥44×44 CSS px | pass, after one fix (§6.3) |
| axe-core serious+critical (WCAG 2.0/2.1 A+AA) | pass, after two fixes and two scoped exceptions (§5) |
| Keyboard focus ring visible | pass |
| Vendor map mounts and shows pins on a phone | pass |
| Usable on throttled 3G | pass (Chromium only — §4.2) |

## 4. What automation could NOT verify

These are capability limits of the test rig, stated plainly rather than left to
look like coverage.

### 4.1 Logged-in journeys on iOS Safari

`agri_sid` is a `Secure` cookie and the local dev servers speak plain http.
Chromium treats `http://localhost` as a trustworthy origin and sends Secure
cookies to it anyway; **WebKit stores the cookie but never sends it**, so
`/api/auth/me` answers `401 {"user":null}` forever. The OTP itself is fine —
`/auth/otp/verify` returns 200 with a valid `otp_proof` and `/auth/login`
returns `status:ok` — only the browser's follow-up requests are anonymous,
which surfaces as the login screen wrongly claiming the code was wrong.

**This is not a product defect.** Production is https, where Safari sends the
cookie normally. It does mean **no signed-in flow has been machine-verified on
WebKit**; see the owner checklist.

### 4.2 Throttled 3G on iOS Safari

Network emulation needs CDP, which only Chromium exposes. `low-data.spec.ts`
skips on WebKit by design.

### 4.3 claim → verify runs once, on desktop

Approving a claim sets an owner, and "E2E Claimable Dairy" is a single row, so
a second project running the same journey in one suite finds it already
claimed — only re-running `seed_e2e_milk.py` resets it. Rather than seed a
business per project, or weaken the test to tolerate an owned fixture (which
would stop proving the approval did anything), the journey runs once end to
end. The claim form is a plain file input and submit button on web-agri, and
the tap-target and locale sweeps already cover responsive rendering.

### 4.4 Anything requiring real hardware

Emulation cannot prove install prompts, true touch accuracy, thermal
behaviour, or real-network performance. See §7.

## 5. Accessibility exceptions

Two `color-contrast` exceptions, each scoped to a **single selector** rather
than disabling the rule — the rule stays live everywhere else:

| Selector | Measured | Required | Why deferred |
|---|---|---|---|
| `.bg-call` | **3.47:1** (white on `--call` #1E9E4A) | 4.5:1 | The known D02 call/rating conflict. That green is fixed by `docs/design-system.md`, and "call > chat > form" wants the button unmistakable. Owner-accepted. |
| `.bg-glass` | fails | 4.5:1 | Translucent header pills over the brand gradient — a signature treatment. Clearing it means visual redesign, not a bug fix. Owner-deferred 2026-07-28. |

Both are design decisions, not oversights. Changing either is a design-system
change and belongs to a spec that owns the visual language.

## 6. Defects found and fixed

### 6.1 The vendor map never actually fitted its bounds

`fitBounds()` ran synchronously after the MapLibre constructor, before the
style loaded, so it was silently dropped and the map sat at its **default world
view**. Measured before the fix: only `z=1` tiles ever requested, and all 12
pins rendering within **0.007px** of each other (~83,000 m/px). After moving it
into `map.on("load")`: tiles at `z=12`, pins **16.28px** apart.

CI never caught it because the single-vendor fixture has no second pin to
reveal the collapse — so D24's non-negotiable 3 had effectively never been
verified. Fixed in `vendor-map.tsx`.

### 6.2 Vernacular text failed AA contrast

`.vern` — the mother-tongue line, UX law 1 — carried `opacity: .85`. `--sub` on
`--card` is 5.74:1 on its own, but blending to 85% gives **4.14:1**, under the
4.5:1 floor, with no large-text exemption at `.78em`. axe flagged **19**
instances across home, pincode and post-need.

The vernacular line was the least readable text on the page for the readers who
most need it. Opacity removed in `packages/config/tailwind/preset.js`.

### 6.3 Category chips were under the minimum tap target

Single-line chips measured **40px** tall against the 44px minimum
(`design-system.md` §1.5). The type-filter chips clear it only because their
icon adds a second line. Fixed with `min-h-[44px]`.

Note the sweep honours `.tap-target`, the design system's own mechanism (an
`::after` overlay sized `max(100%, 44px)`): it enlarges the hit area without
changing the element's box, so measuring boxes alone reports compliant controls
— the 18px Data-saver switch, the header location pill, the GPS pill — as
violations. The chips were the one real offender.

### 6.4 Vendor cards nested interactive controls

Cards carried `role="button"` + `tabIndex` while containing the Call and
WhatsApp links: `nested-interactive`, 7 instances. A button wrapping links gives
screen readers a control they cannot describe, and put an extra tab stop before
every card. Click-to-select is unchanged, and map pins are real `<button>`s, so
pin → card still works from the keyboard.

### 6.5 Tamil broke the notifications header on a phone

`ta/notifications` overflowed a 393px Pixel 5 by 15px (408px). The
mark-all-read button sat in a plain flex row pinned `flex-none`, which sizes to
max-content, so a label longer than the space left over pushes the row past the
viewport instead of wrapping. English "Mark all read" is 13 characters and
fits; Tamil is 28 — "அனைத்தையும் படித்ததாகக் குறி" — and does not. Fixed with
`flex-wrap` plus `max-w-full` on the button.

Two things made this easy to miss. The header only renders with **at least one
notification** (an empty inbox renders `EmptyState`), and a fresh signup only
gets one once the notify worker delivers — CI was slow enough, a dev box was
not. And it is font-metric dependent, so it reproduces on the CI runner's font
stack and not necessarily locally. The overflow assertion now names the widest
offending elements, because "the page is 15px too wide" cannot be fixed without
reproducing it otherwise.

This is D29's non-negotiable 2, and it was found only because the matrix runs a
real phone viewport.

### 6.6 Test-harness defects that were hiding real state

- **`/c/milk` is not a category.** `DAIRY_CATEGORIES` is
  `veterinarian | feed-supplier | dairy-farm | cooperative`, so that route 404s
  — and the locale sweep had been passing Next's **error page** in all three
  locales. The sweep now fails on `html#__next_error__`, so an error page can
  never pass silently again.
- **`post-need` answered stale inquiries.** It matched any `status=new`
  inquiry by type+pincode; with 24 accumulated locally it responded to an
  earlier run's need belonging to a different user. Now diffs a pre-post
  snapshot.
- **Position-keyed fixtures.** `vendors[0]` is distance-ordered — a D27 demo
  listing locally, the fixture only in CI. Resolved by slug now.
- **CI had no object storage.** D16 claim evidence uploads through
  `shared.storage`, which is MinIO-backed, and neither e2e job provided it — so
  `_store_evidence` 500s and the claim journey died with a generic "something
  went wrong" naming no cause. Both jobs now start MinIO (as a step, not a
  service: service containers cannot override the image command and
  `minio/minio` needs `server /data`).
- **The suite could adopt the wrong API.** The dev docker stack serves `:8000`
  without `OTP_TEST_PEEK`; probing `/health` could not tell it apart from the
  e2e API, so `reuseExistingServer` took it and ten OTP specs failed with "no
  OTP recorded". The readiness probe now hits a peek-only route.

## 7. Owner-run checklist (real hardware)

Emulation cannot cover these. Tick and date each.

| # | Check | Device | Result | Date |
|---|---|---|---|---|
| 1 | PWA install prompt appears and installs | Android Chrome | | |
| 2 | PWA installs via Share → Add to Home Screen | iOS Safari 16.4+ | | |
| 3 | **Sign in end to end** (blocked in automation — §4.1) | iOS Safari, against https staging | | |
| 4 | Call and WhatsApp CTAs open the dialer / WhatsApp | real Android + iOS | | |
| 5 | Tap accuracy on the pincode page and filters | low-end Android | | |
| 6 | Map pan/zoom stays responsive; device does not overheat | low-end Android | | |
| 7 | Legible in direct sunlight | any phone | | |
| 8 | Real 3G/spotty network feels usable | real SIM, not emulated | | |

## 8. Known open items

| Item | Status | Deadline |
|---|---|---|
| **Web push has never completed a real subscription** | Open. Not a code bug: headless Chromium reports notifications denied and has no FCM channel, so `pushManager.subscribe()` cannot complete in automation. `notify.push_subscriptions` has never held a row. 2-minute manual proof per `docs/runbooks/web-push.md`. `NEXT_PUBLIC_VAPID_PUBLIC_KEY` is inlined at **build** time, so it must be present during `next build` in the deploy pipeline. | **D31**, mandatory before D32 |
| **Issue #45 — landing perf floor 0.80, not 0.90** | Open. D29's time-boxed attempt found the standard lever cannot work: `experimental.optimizeCss` (critters) runs at build time over prerendered HTML, but `ƒ /[locale]/[city]/[pincode]` is dynamically server-rendered, so critical CSS is never inlined for exactly these pages. Reverted. Remaining paths — make the pages static/ISR over covered pincodes, or runtime inlining — are both larger than a QA spec. `cssChunking: false` still does not merge the two stylesheets (25.8KB + 12.3KB; the cost is round trips, not bytes). | before **D32** |
| **Co-located map pins are mutually unclickable** | Open, D24. `VendorMap.spread()` offsets duplicates by 0.0004° (~44m), which is ~1.3px at the zoom `fitBounds` settles on — far too small to separate a 28px marker. The D27 import puts vendors on the pincode centroid, so real data stacks them. Proper fix is clustering/spiderfy, i.e. a feature. `map-sync.spec.ts` works around it by clicking the topmost (last-rendered) pin. | unscheduled |
| **Hindi readers see Tamil sublabels** | Open, by design. `MILK_TYPE_META` hardcodes `vern` as Tamil for every locale — "English + mother tongue" for a TN-first product. Spec D29.C asks for filters *in Tamil*, which holds. Whether `/hi` should carry Hindi sublabels is a product decision. | unscheduled |
| **`.bg-call` / `.bg-glass` contrast** | Open, owner-deferred. See §5. | unscheduled |
| **CI Lighthouse fixture has one vendor** | Open. The gate protects the shell but not listing-count regressions. Deliberately not changed in D29: it would alter the very page issue #45 measures, and the plan gated that on perf clearing first, which it did not. | with #45 |
| **Local Lighthouse is unreliable on Windows** | Informational. Run 3 of 3 crashed (exit 1) during the D29 baseline. Measure perf in CI (ubuntu), not locally. | — |

## 9. Reproducing

```bash
# prerequisites: migrated DB + geo + fixtures
cd backend/core
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe scripts/load_geo.py
.venv/Scripts/python.exe scripts/seed_e2e_milk.py

# full desktop suite
pnpm run e2e

# device matrix (mobile-chrome + mobile-safari)
pnpm exec playwright install webkit   # once
pnpm run e2e:matrix
```

If OTP specs fail with "no OTP recorded", the dev docker API is holding `:8000`
without `OTP_TEST_PEEK` — `docker stop agri-dev-api-1` and re-run.

---

*Perf tracking moved from #42 to [#45](https://github.com/oneuni-in/agri-ecosystem/issues/45): the original issue was deleted, and #45 carries the accumulated findings forward.*
