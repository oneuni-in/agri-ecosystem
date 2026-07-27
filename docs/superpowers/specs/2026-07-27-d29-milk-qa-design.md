# D29 — Full QA + Device Matrix — Design

Date: 2026-07-27 · Branch: `feat/d29-milk-qa` · Spec: `docs/Sprint/sprint3_D23-D32.md` (D29)

## Context

No new features. D29 proves the assembled Milk.in product works for every user, across
every device and locale, and that the seams between prior specs hold when exercised
together — the D13 lesson that seams surface only in combined runs.

What exists today: one Playwright project (Chromium only, `workers: 1`, five dev servers
— web-id 3003, milk 3000, organic 3001, agri 3002) and nine spec files covering auth,
SSO, milk-home's three empty states (D23), post-need→respond→fulfil (D25), the vendor
console (D26), vendor profile and map sync (D24), pincode landing and PWA (D28), and BFF
path traversal.

Gaps against the spec: discover→call (tracked), claim→verify (D16), and the review
round-trip have no e2e coverage. No a11y tooling exists anywhere in the repo. No spec
switches locale. No device projects.

Two facts established during design that shape decisions below:

- `identity_service.assign_role(session, user_id, role_name)` exists
  (`backend/core/modules/identity/service.py:46`), so a moderator fixture seeds cleanly.
  Only the *first super_admin* needs the SQL bootstrap; a scoped role does not.
- There is **no HTTP flag-set endpoint**. Feature flags are a DB table
  (`alembic/versions/0003_feature_flags.py`) read through a cache. Flipping a flag mid-run
  means a DB write plus defeating that cache.

## 1. Suite architecture

Three projects in `e2e/playwright.config.ts`:

| Project | Device | Runs |
|---|---|---|
| `desktop` | Desktop Chrome | everything — current behaviour, unchanged |
| `mobile-chrome` | Pixel 5 descriptor (low-end Android proxy) | `grep: /@matrix/` |
| `mobile-safari` | iPhone 13 / WebKit | `grep: /@matrix/` |

`@matrix` tags the device-sensitive specs: layout, tap targets, locale, a11y, and the core
journeys. Backend-shaped specs (`bff-path-traversal`, `sso`) stay desktop-only — nothing in
them is device-dependent, and running them three times buys nothing.

`workers: 1` stays (scenarios share one backend DB; serialisation is what makes them
deterministic). The `webServer` list is untouched.

## 2. Journeys (spec A)

Already green, gaining a `@matrix` tag only: the three empty states (D23), the post-need
round trip (D25), map sync (D24).

Three new spec files:

- **`e2e/discover-call.spec.ts`** — guest → pincode home → vendor card → vendor profile →
  login-gated Call → login → reveal → assert the `contact_reveal` inquiry row exists via
  API. That is the "tracked" half, asserted against the reveal-attribution contract in
  `backend/core/modules/directory/analytics.py` (`payload.source == 'contact_reveal'`).
- **`e2e/claim-verify.spec.ts`** — login → claimable business (D16 NULL-owner) → file claim
  → moderator approves → assert ownership took effect.
- **`e2e/review.spec.ts`** — login → post review on a vendor → assert pending and not
  publicly visible → moderator approves → assert visible and the rating aggregate updated.

**Moderation runs via authenticated API, not the admin console.** Both new specs drive
their approve step through `APIRequestContext` rather than booting web-admin (port 3004) as
a sixth dev server. This follows the `e2e/post-need.spec.ts` precedent, which already drives
the vendor half through an API context. The `/ops` console is D21 — an ecosystem surface,
not a Milk.in one — and a sixth Next dev server is real CI cost on a `workers: 1` suite.
Consequence, stated plainly: the D21 ops console remains without e2e coverage after D29.

**Subscribe-tier (flag-aware).** `billing_enabled` is off by default and stays off through
launch, so the flag-OFF branch is the live one, and it is already covered
(`e2e/vendor-dashboard.spec.ts:69-73` — premium intent, survives reload). D29 adds the
assertion that the billing API *refuses* while dark, proving the gate holds. It
deliberately does **not** build a flag-ON e2e branch: with no flag-set endpoint that means
a DB write plus defeating the flag cache, and D20's own tests already cover flag-ON at the
API level. "Flag-aware" is read as *the suite respects the flag's real state*, not *the
suite exercises both states*.

## 3. Fixtures

Extend `backend/core/scripts/seed_e2e_milk.py`, preserving its idempotent
check-by-business-name style:

- a **claimable** business at 641001 with a NULL owner, as the claim target
- a **moderator** identity via `assign_role`, for the two approve steps
- **fix the map-sync overlap** — the D27 seed marker currently collides with the fixture
  pin at 641001, which makes `e2e/map-sync.spec.ts` fail locally while CI stays green. That
  masks real local failures in that spec. Move one of the two so local and CI agree.

Sequenced last, and conditionally: adding more vendors so the CI Lighthouse landing fixture
is representative of a real pincode rather than a single listing. It changes the very page
§6 measures, so it happens only *after* the perf gate settles, and is dropped entirely if
perf does not clear — piling listings onto a page that is already failing its floor would
confuse both results.

## 4. Vernacular (spec C) and device matrix (spec B)

**`e2e/locale.spec.ts`**, `@matrix`. For each milk route × en/ta/hi — home, city, pincode
landing, category, vendor profile, search, post-need, my-needs, notifications, offline.
`my-needs` and `notifications` are auth-gated, so the spec logs in once and reuses the
session across locales rather than re-authenticating thirty times:

- no horizontal overflow — `documentElement.scrollWidth <= clientWidth + 1`. Objective and
  catches the layout breaks the spec names.
- no untranslated key leakage — no raw `ui.*` message keys rendered as visible text.
- under `ta`, CategoryTile and filter labels render actual Tamil (non-ASCII), not the
  English fallback. This is the spec's named requirement.
- the locale switcher round-trips without losing the current route.

**`e2e/device-matrix.spec.ts`**, `@matrix`. Tap targets ≥44×44 CSS px on interactive
elements; map renders and pans. D11 already hit tap-target traps, so this is expected to
surface real failures rather than pass first time.

**`docs/qa/d29-device-matrix.md`** — the documented deliverable required by the DoD. A
surface × device table whose automated columns are filled from the CI run, plus a
real-hardware section left as an owner-run checklist with sign-off lines: PWA install prompt
on Android Chrome and on iOS Safari 16.4+, true touch accuracy, map pan/zoom responsiveness
and thermal behaviour. Emulation cannot prove these; the document says so rather than
implying coverage it does not have.

## 5. Throttled 3G (spec D) and accessibility (spec E)

**`e2e/low-data.spec.ts`** — network throttling via CDP `Network.emulateNetworkConditions`.
**Chromium only**: WebKit exposes no CDP, so this spec runs on `desktop` and
`mobile-chrome` and not on `mobile-safari`. The matrix document states that limit
explicitly rather than implying Safari coverage. Asserts that results become visible within
a budget and that images degrade under the low-data toggle (which already persists across
reloads — `e2e/pwa.spec.ts:35`). The budget number is set from a measured baseline during
implementation, not guessed here.

**`e2e/a11y.spec.ts`** — `@axe-core/playwright` at serious+critical impact over six screens
(home, pincode landing, category, vendor profile, post-need, search), plus targeted
assertions for exactly what spec E names: keyboard
`:focus-visible` rings, and accessible names on Call, WhatsApp, and filter controls.

The known D02 call/rating contrast conflict is handled with a scoped `.exclude()` on those
specific selectors, carrying a comment that cites the design-system decision. `color-contrast`
stays live everywhere else. A global `.disableRules(['color-contrast'])` would be the
paper-over the spec forbids.

Real violations found get fixed — that is what spec E asks for. If the list turns out large,
see §8.

## 6. Issue #42 — landing Lighthouse floor, time-boxed

One bounded attempt at the known lever: the two render-blocking stylesheets in the shared
`packages/ui` shell, responsible for roughly 1559ms of a 3664ms LCP render delay on the 3G
profile. `experimental.cssChunking: false` does not merge them and is not retried.

- Clears 0.90 → raise the `lighthouserc.cjs` floor from 0.80 and close #42.
- Does not clear → stop, write findings into #42, leave the gate at 0.80, record it in the
  matrix as known-open.

The shell is shared by every app, so the home page's 0.90 is re-verified either way; it
passes with little headroom and must not regress.

Out of scope and staying so: web push. It needs no code fix — `push-alerts-card.tsx` is
correct and verified up to the browser↔push-service handshake. Headless Chromium reports
notifications denied and has no FCM channel, so `pushManager.subscribe()` cannot complete in
automation. It is a two-minute manual proof in a real browser
(`docs/runbooks/web-push.md`), already slotted for D31 alongside the "verify real SMS" DLT
step. The matrix records it as an open pre-launch obligation.

## 7. CI

New `e2e-matrix` job mirroring `e2e-auth`'s service and env setup, installing
`chromium webkit --with-deps` and running the two mobile projects. It becomes the ninth
required check. `e2e-auth` continues running the full desktop suite unchanged, so the
existing signal is preserved rather than reshaped.

Splitting into a second job rather than lengthening the first keeps runtime bounded and
makes failures attributable to a device rather than buried in one long serial run.

## 8. Stop conditions

Work stops and reports rather than grinding, if:

- axe returns a large violation list beyond the named items,
- tap-target failures span many shared `packages/ui` components,
- the §6 perf time-box expires.

Each is a "scale this down" decision that belongs to the owner, not something to absorb
silently. Anything left undone is stated explicitly with its reason.

## Testing

The deliverable *is* tests, so "how this is tested" means how it is trusted:

- Every new spec must fail before it passes — written against the real surface, confirmed
  red for the right reason, then made green. No spec is committed having only ever passed.
- No `test.skip` on a failing journey. A red test means either a product bug to fix or a
  scope decision to surface under §8.
- Full local gate run (mypy, lint-imports, ruff-format, typecheck) before first push, per
  standing practice.
- The matrix document's automated columns are filled from an actual CI run, not from local
  results or from expectation.
