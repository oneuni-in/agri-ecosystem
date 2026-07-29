# D30 — Security Freeze + DLT Verify — Design

Date: 2026-07-28 · Branch: `feat/d30-milk-security` · Spec: `docs/Sprint/sprint3_D23-D32.md` (D30)

## Context

The pre-launch adversarial sweep of the whole Milk.in surface, plus the production
edge config and the DLT go/no-go. D29 merged (`bddb6a6`) with all 11 CI checks green,
so the surface under audit is the one that will ship.

**The decisive fact, established during design: DLT registration has not been started.**
Approval in India takes days to weeks and is a third-party queue with no lever to pull.
Real signup therefore cannot be live at D32 on the current timeline. D30's
non-negotiable 2 anticipates this — "real SMS verified **OR** launch-gate decision
recorded" — and the recorded decision (below) becomes the deliverable instead.

What already exists and is not rebuilt here:

- `MSG91Driver` with per-purpose DLT template slots (`modules/identity/otp_drivers.py:58`,
  from D07). `get_sms_driver()` is the only selection point; the switch is
  `sms_provider=msg91` plus four secrets.
- App-tier rate limiting: `RateLimiter`, per-IP per-path, Redis-backed, **60 requests
  per 60s** (`shared/security.py:96`, `settings.py:44`).
- Feature-flag gating with a cached read, `flag_enabled(key)` (`shared/flags.py:31`),
  precedent set by `billing_enabled` and `ads_enabled`.
- Two prior audits in the format this one follows: `docs/security/sprint1-audit.md`,
  `docs/security/sprint2-audit.md` (numbered areas → severity roll-up → fix vs defer).

## 1. Scope, split honestly

Two of the five items cannot complete in this environment. That is stated up front
rather than blurred, because a security document that overstates its own coverage is
worse than one with gaps.

| Item | D30 delivers | Actually completes at |
|---|---|---|
| A. Adversarial audit | full audit + Critical/High fixed | **D30** |
| B. DLT / real SMS | signup gate + registration guide + recorded decision | DLT approval (owner-driven) |
| C. Cloudflare | every rule written as a reviewable runbook | **D31** (no origin exists yet) |
| D. k6 | scripts + local relative baseline | D31 (staging gives real numbers) |
| E. Fix triage | every High closed | **D30** |

**Non-negotiables 3 and 4 will not be honestly met when D30 closes.** WAF and rate
limits will not be live at the edge, and the k6 figures will not be production
figures. Both are recorded as deferred-with-reason in the audit's existing
fix-vs-defer section, with the D31 dependency named. Marking them done would be the
kind of soft-disable the spec's DO-NOT list forbids.

The VPS is provisioned at D31 and DNS cutover is D32 (`sprint3_D23-D32.md`), so there
is no origin for Cloudflare to sit in front of during D30. This is a sequencing
reality in the sprint plan, not a decision made here.

## 2. A — the adversarial audit

Output: `docs/security/milk-audit.md`, following the sprint2 shape so findings stay
comparable across sprints.

Areas, matched to the surfaces D23–D29 actually built rather than a generic checklist:

1. **Auth and session.** `/auth/otp/request` and `/auth/otp/verify` are the module's
   only public routes. The `otp_proof` consume contract (single-use, purpose-bound),
   refresh-family revoke invariants, silent-SSO denylist semantics, and the
   `Secure`-cookie behaviour D29 characterised on WebKit.
2. **Contact reveal (D18).** The fail-closed design, per-user daily caps, whether
   reveal attribution can be forged by a caller, and — asserted directly — that no
   phone number appears in any SSR payload for an unauthenticated visitor.
3. **Vendor dashboard IDOR (D26).** Every `business_id`-scoped route: inbox,
   analytics, coverage, products, tier. Can vendor A read or mutate vendor B's data
   by substituting an id.
4. **Public and leads surface.** Needs fan-out and its caps, reviews moderation,
   claim decision routes (the `FOR UPDATE` + capture-before-commit choreography).
5. **Seed data.** What `seed_import` and the D27 demo import would expose if they
   reached production, and the seeded dev phone numbers.
6. **PWA cache (D28).** What the service worker stores, and whether anything
   user-specific can land in a cache shared across sessions on one device.
7. **OWASP checklist** plus the integration-surface sweep the spec names explicitly:
   committed-tree verify, `app_rt` grant matrix, `public_routes` hand-review.

Every Critical/High is fixed in this spec. Each finding that admits one gets a
**regression test** — an IDOR finding becomes a test asserting the 403, not a note in
a document that nothing enforces.

## 3. B — the signup gate and the DLT decision

**Recorded decision: launch D32 with signup gated.** The public, indexed surface —
directory, pincode landing pages, vendor profiles, search — needs no authentication,
so the launch still earns its SEO value. Signup and login sit behind a
"login coming shortly" gate until DLT clears, at which point the gate lifts by
flipping one flag. Nothing ships on the mock driver.

Two layers, because a flag alone can be flipped wrong:

- **`signup_enabled` flag** — the liftable control, same pattern as `billing_enabled`
  and `ads_enabled`, read through `flag_enabled()`.
- **A hard guard: `app_env == "prod"` and `sms_provider == "mock"` refuses,
  unconditionally, regardless of the flag.** (`app_env` is
  `Literal["dev","test","prod"]`, `settings.py:12`; the guard keys on `prod` only,
  so dev and CI are unaffected.) This is what makes the spec's
  "do NOT launch real signup on the mock driver" structural rather than a matter of
  remembering. A flag by itself cannot give that guarantee — someone flips it and
  real users receive nothing.

The gate sits at `/auth/otp/request`, the shared entry point for both signup and
login, and returns a distinct machine-readable code that the web-id login page
renders as the "login coming shortly" notice rather than a generic failure.

Also produced: `docs/runbooks/dlt-registration.md` — the three purpose template slots
in `otp_drivers.py` (login, verify-email, sensitive-action), sender-ID requirements,
and the four msg91 secrets to provision. This exists so the approval clock can start
immediately; it is the longest-lead item to D32 and the only one no code can shorten.

## 4. C — Cloudflare runbook

`docs/runbooks/cloudflare.md`, with concrete rules — paths, thresholds, actions — not
prose, so applying it at D31 is mechanical rather than interpretive.

The load-bearing design point: **the edge tier must be coarser than the app tier.**
The app already limits 60 req/60s per IP per path. An edge limit tighter than that
would absorb traffic the app-level limiter exists to shape, and the per-path signal
(and its metrics) would go dark. So: strict, low-threshold challenges on `/auth/*`;
looser volumetric limits on `covers()` and contact-reveal; managed WAF rules and bot
fight on.

## 5. D — k6 load test

`load/browse.js` (500 VU) and `load/auth.js` (50 VU), run against the local stack and
reported as a **relative baseline**, with the dev-mode caveat stated in the results
rather than buried.

What a local run genuinely finds: N+1 queries, connection-pool exhaustion, and lock
contention under the `covers()` compound keyset. What it cannot establish: a
production p95. Re-run against staging at D31 for figures worth quoting.

## 6. Testing

- Audit findings get a regression test wherever one is possible.
- The signup gate gets unit coverage on **both** layers: flag off → refused; and
  production + mock driver → refused *regardless of flag state*, which is the
  invariant that actually matters.
- Full local gate run (ruff format, ruff check, mypy, lint-imports, pytest,
  typecheck, lint, check:hex) before first push, per standing practice.
- The e2e suite must stay green: D29's `e2e-auth` and `e2e-matrix` both exercise OTP
  login, so the signup gate must default open in dev and CI or it breaks 15+ specs.

## Out of scope

- Applying Cloudflare config (no account access; owner-driven infra policy).
- Sending a real SMS (no credentials, and no approved DLT templates to send against).
- VPS provisioning — that is D31.A.
- Issue #42 (landing perf) — carried from D29, still due before D32.
