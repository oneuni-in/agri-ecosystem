# Sprint 1 adversarial audit (D14, 2026-07-14)

Scope: D06-D13 (identity, coins, audit, notify, RBAC), with explicit focus
on the integration seams no single spec tested. Findings are graded
Critical / High / Medium / Low; the D14 non-negotiable is zero Critical/High
at tag.

## A1. Migration chain integrity (committed tree)

Verified via `git show HEAD:<file>` for every file in
`backend/core/alembic/versions/` (0001-0015): one straight linear chain,
`revision` == the numeric filename prefix for every file, every
`down_revision` resolves to exactly one existing revision, no duplicates,
no orphans. Working tree == committed HEAD for all five 0011-0015 files
(no drift). **No finding — chain is clean.**

Command used (repeatable):
```bash
for f in backend/core/alembic/versions/00{11..15}_*.py; do
  git show "HEAD:$f" > /tmp/committed_$(basename "$f")
  diff -q /tmp/committed_$(basename "$f") "$f" || echo "DRIFT: $f"
done
```

## A2. Role/grant matrix across schemas

`app_rt` grants audited across identity/coins/directory/leads/content/
market/ads/notify/billing/geo/public (blanket loop, `0013_audit_v1.py:99-107`)
plus the two hardened carve-outs:

- `audit.entries`: SELECT+INSERT only for `app_rt`, always (never in the
  blanket loop) — `0013_audit_v1.py:109-113`. Immutable at grant level.
- `coins.ledger_entries`: UPDATE/DELETE revoked from `app` at creation
  (`0012_coins_v1.py:219,221`), re-opened for `app_rt` by the blanket loop
  (`0013_audit_v1.py:101`), re-revoked in `0015_coins_harden_app_rt.py:40`.
  **Current HEAD state: immutable at grant level**, backed by the
  `coins.reject_ledger_mutation` trigger as defense-in-depth
  (`0012_coins_v1.py:201-218`).

Service connections: `api` uses `app_rt` (`docker-compose.dev.yml:10`),
`worker` (coins) uses `app_rt` (`docker-compose.dev.yml:43`), `notify`
worker uses `app_rt` via the same `shared.db.get_sessionmaker`
(`shared/db.py:122`). No service found using `app` for runtime traffic in
the committed dev compose file. `app` is the migration/table-owner role
(`DATABASE_ADMIN_URL`), never a connecting role for app traffic.

**No finding for dev.** Staging (`docker-compose.staging.yml` reads from
`secrets/staging.env`, not in the repo) could not be verified from
committed files — recorded as an open assumption, not a Critical/High
(no evidence of a problem, just no evidence either way).

## A3. Event-stream contract

Events on the `identity` stream and their consumers:

| Event | Emitted | Consumed by |
|---|---|---|
| `user.registered` | `session_router.py:160-169` (new user, login) | `coins/worker.py:38` (signup_complete award + referral attribution) |
| `identity.signup_completed` | `session_router.py:184-188` | `notify/consumers.py` EVENT_ROUTES |
| `identity.login_new_device` | `session_router.py:190-194` | `notify/consumers.py` EVENT_ROUTES |
| `identity.role_changed` | `admin_router.py:254-260` | `notify/consumers.py` EVENT_ROUTES |
| `identity.session_resumed` (new, D14 Task 8) | `session_router.py` `/auth/me` | `coins/worker.py` (daily_visit award) |

Both consumers (`notify/consumers.py` dict-lookup, `coins/worker.py`
if/elif) are **presence-based / tolerant of unknown event types** — an
unexpected event on the stream cannot break consumer logic.

**Low finding (not fixed in D14, flagged only):**
`backend/core/tests/test_session_router.py:209` and `:240` assert exact
`len(entries) == N` on the login flow's published events. These will need
updating the moment a future spec adds another event inside `login()`'s
new-user/new-device branches. `test_identity_user_registered.py:76` uses a
tolerant `.count(...)` pattern instead — that's the safer style for new
tests. Recording this as a Low style note for D15+, not fixing it now (the
counts are currently correct; changing test style is unrelated churn).

`EVENT_STREAM = "identity"` is independently defined (same value) in three
files (`session_router.py:60`, `profile_router.py:52`, `admin_router.py:46`)
— duplication, not a bug; a D13 plan note already flagged consolidating it
as a future nice-to-have.

## A4. Shared header component (AuthCluster)

Confirmed **exactly one** coins pill renders per header, across all 4 apps
(`web-agri`, `web-organic`, `web-milk`, `web-admin` `site-header.tsx`), via
each app's own `<CoinsBalancePill>` placed as a sibling of `<AuthCluster>`
— `AuthCluster` itself (`packages/auth-client/src/react.tsx:81-98`) renders
only the avatar/login-button, no widgets, no dead/commented branches.
**No duplication finding.** Task 7 adds an explicit "this is the
integration point, put siblings not internals" comment so a future spec
doesn't regress this.

## A5. BFF path-traversal

**Medium finding, fixed in Task 6.** All 8 `[...path]` catch-all proxies
(`web-admin/coins,admin`, `web-agri/coins,notify`, `web-milk/coins,notify`,
`web-organic/coins,notify`) build the upstream URL as
`new URL(`${API}/<prefix>/${path.map(encodeURIComponent).join("/")}`)`.
`encodeURIComponent` does not escape `.`, so a raw `..` path segment
survives into the URL string; `new URL()`'s WHATWG dot-segment
normalization then silently collapses it, which can strip the intended
`/coins`, `/admin`, or `/notify` prefix and retarget the request at a
sibling backend prefix on the same host (it cannot escape the origin, only
the intended path prefix). The route header comment's claim ("Only the
backend's /X prefix is reachable through this route by construction") was
not actually enforced by any code. Backend RBAC still gates every route
regardless of which BFF proxy reached it, so this was defense-in-depth
missing, not a full authz bypass — graded Medium, not High, on that basis.
Fixed by rejecting any `.`/`..`/empty path segment up front, before the
auth check, in all 8 files (Task 6).

## A6. Generic attack surface

<!-- Task 5 appends its findings here -->

## Part B deferred-items decisions

<!-- Tasks 11-13 append the decision table here -->
