# GATE 2 evidence (D14, 2026-07-15)

Definition of done: zero Critical/High open at tag; backend-storm required
before tag; committed tree verified == tested tree; every box below checked
and dated; v0.2.0 promotable from main.

## Checklist

- [x] one AgriID -> login on all 3 site domains (localhost multi-port) via SSO

  `e2e/sso.spec.ts` (2/2 passing, full suite run 2026-07-15):
  ```
  ok e2e\sso.spec.ts:14:5 › login once on milk -> in on organic -> logout-everywhere kills both (24.7s)
  ok e2e\sso.spec.ts:79:5 › silent SSO probe fails gracefully for a fresh visitor (4.9s)
  ```
  Covers login on `web-milk` (3000) with silent-SSO pickup on `web-organic`
  (3001) via `web-id`'s (3003) session — the three-domain SSO path.

- [x] logout-everywhere across apps

  `e2e/auth.spec.ts::logout-everywhere kills both devices at once` (PASS,
  10.9s) and `e2e/sso.spec.ts`'s combined login+logout-everywhere scenario
  above (PASS) — both devices/domains confirmed signed out in one request
  cycle.

- [x] OTP abuse suite green incl. manual burst

  Automated: `backend/core/tests/test_otp_service.py` (14/14, includes the
  2 new real-multi-connection concurrency tests from Task 14 Fix 1) and
  `backend/core/tests/test_otp_throttle.py` (13/13, includes the new
  concurrency test from Task 14 Fix 2) — both part of the 507-passed full
  suite run (2026-07-15).

  Manual burst (Task 16, against a live `uvicorn` instance on
  `127.0.0.1:8000`, not pytest):
  ```
  === Concurrent OTP flood: 8 simultaneous /auth/otp/request for +919887654321 ===
  req1 status=200 {"status":"sent"}
  req2 status=429 {"detail":"rate_limited"}
  req3 status=429 {"detail":"rate_limited"}
  req4 status=429 {"detail":"rate_limited"}
  req5 status=429 {"detail":"rate_limited"}
  req6 status=429 {"detail":"rate_limited"}
  req7 status=429 {"detail":"rate_limited"}
  req8 status=429 {"detail":"rate_limited"}
  ```
  8 genuinely concurrent requests (backgrounded curl + `wait`) for a fresh
  phone number, exactly 1 succeeded — proves Task 14 Fix 2's atomic cooldown
  claim holds against a live running server, not just under pytest.

- [x] 10k-award storm zero drift — AND backend-storm is a required status check

  `backend/core/tests/test_coins_storm.py::test_storm_no_drift_no_negative`:
  passed against the working tree (Task 15, ~7m54s) AND independently
  re-passed against the archived committed tree (Task 17, ~7m20s). 10,000
  concurrent operations, zero balance drift, zero negative balances both
  times.

  `backend-storm` documented as the 9th required CI check in
  `docs/runbooks/branch-protection.md` (Task 2, commit `143a164`). **Caveat
  carried forward from Task 2/D13**: GitHub branch-protection/ruleset
  enforcement is not active on this repo's free plan (known gap, unchanged
  since Gate 1) — the check is documented and will activate automatically on
  a Team-plan upgrade, but adding it to the live GitHub ruleset today is an
  owner action pending as of this gate (see `branch-protection.md`'s
  verification log, 2026-07-14 entry).

- [x] migration chain verified on the COMMITTED tree (A1)

  `docs/security/sprint1-audit.md` A1 section (Task 4): linear 0001->0015
  chain, no duplicates/orphans, filename<->revision match, verified via
  `git show HEAD:<file>` against every migration file.

  Re-verified independently in Task 17 against a fresh `git archive HEAD`
  extraction: `alembic history` loaded the identical clean chain from the
  archived copy (confirmed via a direct `python -c "import modules...; print(__file__)"`
  check that the archive, not the editable-installed working tree, was
  actually what got imported and tested).

- [x] app_rt grant matrix correct across all 4 schemas; no service connects as `app` at runtime (A2)

  `docs/security/sprint1-audit.md` A2 section (Task 4): `coins.ledger_entries`
  and `audit.entries` both immutable at grant level for `app_rt`; `api`,
  `worker` (coins), and `notify` worker all confirmed connecting as `app_rt`
  in `docker-compose.dev.yml`; `app` is migration-only (`DATABASE_ADMIN_URL`).

  Re-proven live in Task 15/17: `test_app_rt_cannot_update_or_delete` and
  `test_runtime_url_is_app_rt_and_admin_url_is_app` both pass when the test
  suite is run with the CORRECT runtime role
  (`DATABASE_URL=postgresql+asyncpg://app_rt:app_rt@...`) — an earlier
  same-session run with the wrong `app:app` URL correctly failed these two
  tests, which is itself a live demonstration that the grant/role
  distinction is real and enforced, not just documented.

- [x] exactly one coins pill per header; AuthCluster documented as the header integration point (A4)

  `docs/security/sprint1-audit.md` A4 section (Task 4): confirmed exactly
  one `<CoinsBalancePill>` per header across all 4 apps, as a sibling of
  `<AuthCluster>`, not inside it.

  `packages/auth-client/src/react.tsx`'s `AuthCluster` doc comment (Task 7,
  commit `35ec76b`) now explicitly states: "THIS IS THE HEADER INTEGRATION
  POINT (D14 A4): future header widgets ... belong as SIBLINGS of
  `<AuthCluster/>` ... never render them FROM INSIDE this component" — with
  the two D13 mistakes (duplicate pill, then a dead placeholder field) named
  as the reason, so a future spec doesn't repeat either.

- [x] public_routes.txt hand-reviewed — every public route justified in one line

  `backend/core/public_routes.txt` (10 declared routes), reviewed 2026-07-15:

  | Route | Justification |
  |---|---|
  | `/health` | Liveness probe — must be reachable pre-auth for orchestration/uptime monitoring. |
  | `/health/deep` | Deep dependency check (DB/Redis) — same operational necessity, no user data returned. |
  | `/metrics` | Prometheus scrape endpoint — internal-network-only in practice, no auth mechanism exists for scrapers. |
  | `/auth/otp/request` | Entry point of the OTP login flow itself — cannot require auth (that's what it's issuing). Rate-limited (`otp_throttle.py`). |
  | `/auth/otp/verify` | Completes the OTP flow — same reasoning; rate-limited, enumeration-resistant per A6 audit. |
  | `/auth/login` | Exchanges a verified `otp_proof` for a session — pre-session by definition. |
  | `/authorize` | OAuth2 authorization endpoint (D08) — standard OAuth surface, public per spec, PKCE-protected. |
  | `/token` | OAuth2 token endpoint — public per OAuth2 spec, client-authenticated via PKCE code verifier. |
  | `/oauth/revoke` | Token revocation endpoint — standard OAuth2 public surface (RFC 7009). |
  | `/.well-known/jwks.json` | JWKS discovery — must be publicly fetchable for any relying party to verify tokens; contains only public keys. |

  All 10 routes are either pre-auth necessities (OTP/login/health) or
  standard OAuth2 public surface (authorize/token/revoke/jwks) — no
  route exposes user data or a mutating action without authentication. No
  undeclared-public-route drift: `python scripts/dump_public_routes.py --check`
  is exercised by the `public-routes` CI job on every PR and was green
  throughout D14 (no route additions/removals this sprint).

- [x] audit verify_chain() clean over sprint's real data

  `backend/core/tests/test_audit_integrity.py` (4/4: intact-chain-verifies,
  tampered-row-breaks-chain, deleted-row-breaks-chain, app_rt-cannot-update-
  or-delete) — part of the 507-passed full suite.

  Live run against the actual dev database (2026-07-15):
  ```
  $ python scripts/verify_audit_chain.py
  {"ts": "2026-07-15T07:49:22.828+00:00", "level": "INFO", "logger": "__main__", "msg": "audit chain verified", "request_id": null, "breaks": 0}
  ```
  Zero chain breaks over the sprint's accumulated real audit data, including
  every new `coins.manual_adjust` and `coins.rule_updated` entry written by
  Task 14's Fix 4/Fix 5.

- [x] git status clean, zero AM files, committed tree == tested tree

  `python scripts/check_fully_staged.py` (Task 3's own gate, run before every
  commit throughout D14): `check_fully_staged: OK` on every invocation,
  confirmed again immediately before writing this gate document.

  Committed tree == tested tree: proven directly in Task 17 — a fresh
  `git archive HEAD` extraction, verified to actually be what Python
  imports (not the editable-installed working-tree copy), passed the full
  507-test suite, the 10k-op storm test, and all static checks
  (ruff/mypy/lint-imports) identically to the working-tree runs. This is the
  exact D13 near-miss (committed content silently diverging from what was
  locally tested) re-verified clean for D14.

## Critical/High findings: zero open

All 5 Critical/High findings from the Part A6 adversarial audit
(`docs/security/sprint1-audit.md`) are fixed, independently re-verified by
a task reviewer against real code/tools (not just the implementer's
self-report) for each:

1. OTP `verify_otp` attempts lost-update race (Critical) — `ccebef9`
2. OTP issue-cooldown race (High) — `1fcfc28`
3. RBAC `reactivate_user` missing super-admin-target guard (High) — `6351d8d`
4. coins `adjust_confirm` audit-orphan (Critical) — `91c7dc6`
5. coins `update_rule` zero audit trail (High) — `edd26af`

38 total A6 findings recorded (2 Critical, 3 High, 9 Medium, 8 Low, 16
Informational); every Critical/High is `fixed`, all others recorded as
`open` with severity-appropriate reasoning (not blockers per the D14
non-negotiable, which scopes zero-tolerance to Critical/High only).

## Part B deferred-items: all 7 resolved

Fixed now: BFF path-traversal hardening (Task 6), daily_visit award wiring
(Task 8), AbuseFlagOut details field (Task 9), dead coinsBalance removal
(Task 10). Explicitly deferred with documented reasoning: referral-cap
TOCTOU (Task 11, pinned to the single-worker constraint), unused seeded RBAC
perms (Task 12), ta/hi translation content review (Task 13) — see
`docs/security/sprint1-audit.md`'s "Part B deferred-items decisions" table.

## Known gaps carried forward

- Branch protection / rulesets remain unenforced on the free GitHub plan
  (`docs/runbooks/branch-protection.md` Known Gap, unchanged since Gate 1) —
  `backend-storm` is documented as required (Task 2) but activation on the
  live GitHub ruleset is an owner action, still pending as of this gate.
- `web-admin` and `web-agri` are not in `e2e/playwright.config.ts`'s
  `webServer` list, so their BFF proxy hardening (Task 6) was verified by
  unit-identical code across all 8 files + one live manual curl each
  (`web-admin`'s admin proxy confirmed returning Next's own 404 for both
  encoded and literal traversal payloads), not full automated e2e —
  pre-existing gap, not introduced or expanded by D14.
- Referral-cap TOCTOU (Part B#1) and unused RBAC perms (Part B#4) are
  explicit, documented defers — see `docs/security/sprint1-audit.md`.
- The stray `dev` commit (`8afc805`, "day 13") extraction is in progress as
  a separate `chore/dev-harness-sync` PR (Task 1) — pending human merge as
  of this gate; does not block this branch's own readiness since it only
  affects `dev`'s own history hygiene, not this branch's content.
- 33 non-Critical/High A6 findings remain `open` (9 Medium, 8 Low, 16
  Informational — Task 14 fixed only the 5 Critical/High rows, per this
  spec's explicit scope) — recorded in `docs/security/sprint1-audit.md` for
  Sprint 2 triage; none are launch blockers per this gate's
  Critical/High-only non-negotiable.
