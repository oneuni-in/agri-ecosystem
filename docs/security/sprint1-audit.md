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

**Low finding (downgraded from an initial Medium during Task 6 — see
below), fixed in Task 6.** All 8 `[...path]` catch-all proxies
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
missing, not a full authz bypass. Fixed by rejecting any `.`/`..`/empty path
segment up front, before the auth check, in all 8 files (Task 6).

**Severity correction found during Task 6's TDD:** the guard's own test
(`e2e/bff-path-traversal.spec.ts`) could not be made to observe a live `..`
segment reaching `params.path` through any genuine HTTP request. Four
independent request methods — `curl`, Node's `http.request`, a raw TCP
socket writing the HTTP request line by hand, and Playwright's own
`request` fixture — all confirmed the same root cause: Next.js 15's App
Router normalizes literal and percent-encoded (`%2e`) dot-segments in the
incoming request's pathname *before* route matching and *before*
populating a `[...path]` catch-all's `params.path` array. Concretely,
`/api/coins/%2e%2e/%2e%2e/admin/rules` collapses to `/admin/rules` at
Next's own front door, matching no route in the requesting app (its own
404, never reaching our handler); `/api/coins/./balance` collapses
harmlessly to `/api/coins/balance`. Manually verified the same holds for
`web-admin`'s admin proxy (port 3004): both `%2e%2e`-encoded and literal
`../../` traversal payloads against `/api/admin/../../coins/rules` returned
Next's own `404`, before ever reaching the guard.

**Net assessment:** the practical exploitability of this specific vector —
a client sending `..`/`%2e%2e` segments over real HTTP to a live Next.js
App Router `[...path]` route — is already neutralized at the framework
layer, independent of whether the 8-file guard exists. Downgraded from
Medium to **Low** on that basis. The guard itself is kept as legitimate
defense-in-depth (it protects any future code path that constructs the
`path` array from a source Next itself doesn't normalize, or against a
Next config/version change that stops normalizing) — not reverted, just no
longer treated as the primary mitigation for this vector.
`e2e/bff-path-traversal.spec.ts` now asserts the discovered Next.js
front-door behavior directly (404/404/401 for the three payloads) as a
regression guard: if that test ever starts failing, it signals the
normalization assumption changed and the guard's HTTP-reachability needs
re-verifying.

## A6. Generic attack surface

Six parallel hostile-auditor passes (read-only, against committed HEAD on
`feat/d14-sprint1-hardening`), one per surface: (1) OTP flooding/brute-force/
enumeration/race, (2) OAuth code replay/PKCE/redirect-URI/state, (3) session
rotation races/family-revoke/fixation, (4) RBAC escalation/IDOR, (5) coins
idempotency/caps/referral-farming/negative-balance, (6) audit chain gaps/
notify spam. Every Critical/High finding below was then independently
re-verified by a second adversarial pass whose only job was to refute it
(reproduce the failure or find a nearby mitigating check); all five were
**CONFIRMED**, none refuted this round. Fixes are out of scope for this task
(they land in Task 14) — this table is the audit record only.

| Severity | Area | File:line | Description | Status |
|---|---|---|---|---|
| Critical | OTP | `backend/core/modules/identity/otp_service.py:122-146` | `verify_otp` reads `attempts` with a plain `SELECT` (no `FOR UPDATE`, no optimistic lock) then writes `attempts=<python-computed literal>` on flush. Concurrent verify requests against the same active OTP each read the same stale count and each independently write `old+1`, a genuine lost-update — `OTP_MAX_ATTEMPTS=3` never trips under concurrent guessing, so the 6-digit code can be brute-forced with far more than 3 tries inside its TTL. | confirmed — independent re-read of `otp_service.py`, `shared/db.py`, and `OtpRequest`'s mapper confirms no locking/version column anywhere in the path; Postgres READ COMMITTED row-locking on the blind `UPDATE` does not prevent the second writer from clobbering with the same stale value. |
| High | OTP | `backend/core/modules/identity/otp_service.py:78-102`, `backend/core/modules/identity/otp_throttle.py:76-97,100-126` | The resend-cooldown key (`otp:cd:{phone}`) is only written at the end of `register_issue`, after the DB update/insert/flush; `assert_issue_allowed`'s cooldown check is a plain TTL read with no atomic claim-the-slot (`SET NX`) beforehand. Concurrent `/auth/otp/request` calls for the same phone all pass the cooldown gate before any of them writes it, letting an attacker burn a victim's daily OTP quota (and send multiple SMS) in one synchronous burst instead of the intended 30s/60s/300s escalating pacing. | confirmed — independent trace of the exact Redis/DB call order confirms `assert_issue_allowed` and `register_issue` are two non-atomic operations separated by an awaited DB flush, with no `SET NX EX` anywhere in the path; only the atomic daily cap (5/day) bounds total volume, not per-request pacing. |
| Medium | OTP | `backend/core/settings.py:46`, `backend/core/modules/identity/otp_service.py:52-54` | `otp_pepper` defaults to the hardcoded literal `"dev-only-pepper"` with no startup fail-closed check (unlike `get_signing_key()`, which hard-fails boot if the OAuth key is missing). If `OTP_PEPPER` is omitted in prod, the app boots normally using a pepper value visible in this repo, silently defeating the documented "DB dump alone can't offline-brute the code space" guarantee. | open |
| Low | OTP | `backend/core/modules/identity/otp_service.py:133-148` | Timing side-channel: the "no active code" branch never calls `session.flush()`, while the "active code, wrong guess" branch always does an extra DB round-trip — response timing differs measurably, letting an attacker probe whether a target phone currently has a live OTP outstanding. | open |
| Low | OTP | `backend/core/modules/identity/router.py:62-73` | `OtpVerifyIn.code` is a bare `str` with no `max_length`/digit-pattern validator (unlike `phone`, which is strictly normalized); `device_fingerprint` likewise has no length cap. Low cost today (cheap HMAC hashing) but a missing basic input-validation control. | open |
| Informational | OTP | `backend/core/modules/identity/router.py:167-195`, gated at `backend/core/main.py:157-159` | `/auth/otp/_peek` (returns the live code for any phone, no auth) and `/auth/otp/_reset` (wipes throttle state for any phone) mount whenever `otp_test_peek=true` and `app_env != "prod"` — a documented E2E escape hatch gated by one settings boolean only; if a reachable staging box leaves the flag on, every OTP control in this table is bypassed. | open |
| Informational | OTP | `backend/core/modules/identity/otp_throttle.py:96-97`, `router.py:64` | `OTP_ISSUES_PER_DEVICE_PER_DAY` keys on a client-supplied, unauthenticated `device_fingerprint` — trivially bypassed by randomizing/omitting it. Not independently exploitable since the phone/IP caps are the real backstop. | open |
| Informational | OTP | `backend/core/shared/security.py:47-48,104-108`; `Dockerfile:22` | Forward-looking trap, not a live bug today (no reverse proxy configured yet per D14 memory): per-IP OTP/rate-limit buckets key on `request.client.host`; once a reverse proxy is introduced, uvicorn must be started with `--forwarded-allow-ips` pinned to the proxy's exact IP or every per-IP throttle either collapses into one shared bucket or becomes spoofable via `X-Forwarded-For`. | open |
| Informational | OAuth | `backend/core/modules/identity/oauth_router.py:106-109,121-123` | Success and `prompt=none` redirects are built with hardcoded `f"{redirect_uri}?code=...&state=..."` string concatenation instead of authlib's own `add_params_to_uri`. Harmless today (seeded redirect_uris are bare paths with no existing query string) but would silently corrupt the `code` param if a future client's redirect_uri ever carried one. | open |
| Informational | OAuth | `backend/core/modules/identity/session_auth.py:46-51` | `resolve_bearer_token` does not check the `aud` claim — an access token minted for one first-party client (e.g. `web-milk`) is equally valid as a bearer credential against any other first-party client's endpoints. Deliberate v1 tradeoff (all clients equally trusted today); becomes a real gap if a lower-trust client is ever onboarded. | open |
| Informational | OAuth | `backend/core/modules/identity/oauth_router.py:145-190` | The authorization code is consumed and a refresh-token family is minted and committed *before* authlib's PKCE/redirect_uri/user checks run ("burn-on-attempt" design). A process crash in that narrow window can leave an orphaned, never-cleaned-up refresh-token family in `sessions_refresh` — not exploitable (the plaintext token never left the server), but untracked DB litter. | open |
| Medium | Sessions | `backend/core/modules/identity/session_auth.py:42-64` | Access tokens are stateless RS256 JWTs with no `jti`/family/session claim; `resolve_bearer_token` verifies signature/iss/exp/sub and re-checks user *status* but never checks whether the refresh family or web session that spawned the token is still alive. Logout, logout-everywhere, admin-suspend, and theft-triggered family revoke all leave any already-minted access token valid for up to its full 15-minute TTL after "revocation." | open |
| Medium | Sessions | `backend/core/modules/identity/refresh_service.py:193-228` | The two genuine theft-detection paths (replay of a rotated/revoked refresh token; device-fingerprint mismatch) call `revoke_family()` but only `logger.warning(...)` — neither calls `shared.audit.audit()` nor pushes a backchannel/notify event, unlike voluntary logout or admin-suspend in the same module. The single most security-critical event in this module gets a weaker automated response than a routine logout. | open |
| Low | Sessions | `backend/core/modules/identity/session_service.py:28-36` | `device_fingerprint()` hashes only client-supplied `User-Agent` + `Sec-CH-UA-Platform` headers, no server-side secret or TLS-channel binding — the "device mismatch → theft" signal in `rotate_refresh_token` is fully attacker-controllable by replaying the same two headers alongside a stolen token. | open |
| Low | Sessions | `backend/core/modules/identity/refresh_service.py:183-213` | Not attacker-exploitable (self-DoS only): a benign double-submit of the *same* refresh token (mobile retry-on-timeout, duplicate tab) is indistinguishable from theft-replay, so the second submitter's request revokes the whole family including the just-issued legitimate successor, force-logging-out the real device. | open |
| Informational | Sessions | `backend/core/tests/test_refresh_rotation.py` | No test exercises true concurrent DB transactions (`asyncio.gather` with two real sessions) for the rotation race — the module's own "race" claims are validated only by sequential logic, relying on Postgres row-lock semantics rather than repo test evidence. | open |
| Informational | Sessions | `backend/core/modules/identity/oauth_router.py:179-190` | Same commit-before-full-response-serialization pattern noted under OAuth above, re-confirmed from the session/refresh-family angle: a crash between the pre-authlib commit and response delivery can orphan a refresh family with no cleanup. | open |
| High | RBAC | `backend/core/modules/identity/admin_router.py:328-340` | `reactivate_user` (permission `users.suspend`, held by the `staff` role per `0008_identity_seed_roles.py:50`) never calls the `_guard_suspend_target` check that `suspend_user` uses at line 310. A `staff`-role principal can therefore unilaterally reactivate a `super_admin` account that was suspended for incident response, with no super_admin-level authorization on the reactivate side — breaking the exact escalation-guard symmetry the suspend side enforces. Untested: `test_admin_router.py`'s only related test covers suspend, not reactivate, against a super_admin target. | confirmed — independent re-read confirms `staff` genuinely holds `users.suspend` (seed migration), `reactivate_user` calls no guard of any kind, and `require_permission`/`SecureRouter` have no built-in role-hierarchy logic that would otherwise close the gap. |
| Informational | RBAC | `backend/core/modules/identity/rbac.py:9-12,31-56` | Role→permission matrix cache has a 30s TTL with `reset_permission_cache()` only ever called from tests — not exploitable today (no live endpoint mutates `role_permissions`), but a latent trap for the first future endpoint that does. | open |
| Informational | RBAC | `backend/core/modules/identity/admin_router.py:217-221` | `_guard_super_admin` hardcodes the literal string `"super_admin"` rather than a role-tier concept — theoretical only, since `roles.assign` is currently seeded exclusively to `super_admin`. | open |
| Informational | RBAC | `backend/core/modules/identity/admin_router.py:229-248` | `add_role`/`remove_role` resolve the target user (404) before the super-admin guard (403), giving a caller who already holds `roles.assign` a trivial existence-oracle — no practical value since that caller already has `users.read`. | open |
| Medium | Coins | `backend/core/modules/coins/rules.py:60-81` | `check_numeric_caps` is count-then-insert with no advisory lock/`FOR UPDATE`. Dormant today (every seeded rule has `cap <= 1`, enforced instead by the idempotency-key unique constraint), but activates the moment `coins_rules_admin` raises any cap above 1 with no compensating lock added by that admin path. | open |
| Medium | Coins | `backend/core/modules/coins/referrals.py:133-149` | Referrer monthly-cap check (`rewarded_this_month`) is an unlocked `SELECT count()` then conditional award — two concurrent `profile.completed` events for different referees of the same referrer can both observe `count==19` and both award, breaching `REFERRER_MONTHLY_CAP=20`. Mitigated today only by the operational fact of a single coins-worker replica, not by any code-level guard. | open |
| Medium | Coins | `backend/core/modules/coins/worker.py:54`, `backend/core/modules/identity/session_router.py:133,160-169` | Device-fingerprint referral-farming detection is dead in production: the fingerprint computed in `session_router.py` is never included in the `user.registered` event payload, so `worker.py` always calls `referrals.attribute(..., device_fingerprint=None, ...)` and `abuse.py`'s device-clustering branch can never populate — only the coarse 4-character phone-prefix signal is live. | open |
| Medium | Coins | `backend/core/modules/coins/abuse.py:15-52` | `scan_clusters()`, the only mechanism that turns farmed-looking referral clusters into `AbuseFlag`s for admin review/void, is never invoked outside tests — no cron/CI/admin-route trigger exists anywhere in the repo, unlike `integrity.py` which at least has a runnable `scripts/coins_integrity.py` entrypoint. A referral farm can accumulate indefinitely with no flag ever created. | open |
| Medium | Coins | `backend/core/modules/coins/admin_router.py:93-103,183-241` | `AdjustIn.delta` has no magnitude bound (only non-zero validated), and the dual-confirm flow is an explicit two-step-not-two-person control with no per-admin daily/aggregate cap — only the generic 60 req/60s per-IP-per-path rate limit applies, which is not admin-specific. A single compromised `super_admin` credential can sustain large drains indefinitely. | open |
| Low | Coins | `backend/core/shared/security.py:104-108` | `rate_limit` keys on raw `request.client.host` with no documented reverse-proxy/`X-Forwarded-For` handling for the admin-mutating coins routes specifically — same forward-looking proxy trap noted under OTP, called out again here because it's the layer standing between a scripted admin and unlimited adjust/rule-change velocity. | open |
| Low | Coins | `backend/core/modules/coins/rules.py:60-81`, `referrals.py:141-148` | Cap-check queries (`COUNT` over `ledger_entries`/`referrals` filtered by user/referrer + time window) have no covering composite index — a mild amplification vector at scale if cap-checked rules become numerous or high-traffic. | open |
| Informational | Coins | `backend/core/modules/coins/rules.py:32-46` | `daily_visit`'s `deterministic_key` takes a caller-supplied `day` argument rather than deriving it from a trusted server clock inside the function. No live caller exists yet (test-only today), but this must be server-derived, not client-supplied, once the rule is wired to a real endpoint. | open |
| Critical | Audit/Notify | `backend/core/modules/coins/admin_router.py:231-240` | `adjust_confirm` (manual coin-balance adjustment, dual-confirm flow) calls `publish("audit", "coins.manual_adjust", {...})` — a bare Redis-stream `xadd` — instead of `shared.audit.audit()`. No consumer anywhere in the repo subscribes to a stream named `"audit"` (notify's worker reads `("identity","notify")`; coins' worker reads `"identity"` only), so the event is permanently orphaned. The admin's `reason_note` justification exists only as a short-TTL Redis key that is `getdel`'d earlier in the same handler and is not a column on `LedgerEntry` — it becomes unrecoverable the instant the handler returns. The module's own docstring claims this flow is "audit-logged"; it is not, in practice. | confirmed — independent re-read confirms `shared.audit` is never imported in this file, no consumer group exists on the `"audit"` stream repo-wide, and `LedgerEntry` has no free-text column; no reconciliation job or hidden bridge was found. |
| High | Audit/Notify | `backend/core/modules/coins/admin_router.py:160-173` | `update_rule` (`PUT /admin/coins/rules/{code}`, lets a `super_admin` change a coin rule's amount/caps/active flag/validity window) has **no** audit call and **no** event publish of any kind — not even the (separately flagged) broken `publish("audit", ...)` pattern used elsewhere in this same file. A `super_admin` can silently change reward economics system-wide with zero trace beyond the overwritten row; `coins.rules` has no history table and the ledger's immutability trigger is scoped only to `ledger_entries`, not `rules`. | confirmed — independent re-read confirms no audit/publish call anywhere in the handler body, no router-level audit dependency applied uniformly to `admin_router.py`, and no history/versioning table or trigger on `coins.rules`. |
| Medium | Audit/Notify | `backend/core/modules/coins/admin_router.py:326-330` | `void_abuse` uses the same dead `"audit"`-stream pattern as `adjust_confirm` above, so it also never lands in `audit.entries`. Lower impact than the Critical finding because the resulting state change is reconstructible from other tables (`AbuseFlag.reviewed_by/reviewed_at`, `Referral.status`, the compensating `LedgerEntry` rows). | open |
| Informational | Audit/Notify | `backend/core/shared/audit.py:104-113`; `0013_audit_v1.py:108-113` | The chain's self-documented hole — deleting the *newest* entry of a day leaves nothing downstream to reference it, so `verify_chain()` cannot detect a tail deletion — is genuinely closed today by the grant matrix (`app_rt` has SELECT+INSERT only, pinned by `test_audit_integrity.py`), but is a single point of failure: if `DATABASE_URL` is ever pointed at an owner/superuser role in some future environment, this protection silently vanishes with no compensating detective control. | open |
| Informational | Audit/Notify | `backend/core/shared/audit.py:105-129` | Verified sound: `audit()` acquires `pg_advisory_xact_lock(hashtext('audit:<day>'))` before reading the "last" row, so two concurrent writers cannot both read the same prior row and fork the chain; `verify_chain()`'s break-recovery logic avoids cascading a single tampered/deleted row into a flood of false positives. No finding — recorded for completeness. | open |
| Low | Audit/Notify | `backend/core/shared/audit.py:106` | The advisory lock key (`audit:{day}`) is a single global lock shared by every audited action app-wide for a given calendar day, held for the caller's whole DB transaction (not just the `audit()` call) — a coarse contention/availability risk under load, not a correctness bug. | open |
| Low | Audit/Notify | `backend/core/modules/notify/service.py:57-64` | `_within_rate_cap`'s 30/hour cap uses a fixed hour-bucket key, not a sliding window — a victim could receive up to ~2x the intended cap across an hour boundary. No practical unbounded-spam vector found on the currently reachable endpoint surface (every notify-triggering action already requires authentication as, or elevated permission over, the victim). | open |
| Informational | Audit/Notify | `backend/core/modules/notify/worker.py:29-49` | Self-documented known gap: if `session.commit()` succeeds but the process dies before `consumer.ack(event)`, the event is stuck forever (no idle-based `XCLAIM`/`XAUTOCLAIM` reclaim wired in) — a lost-notification/availability bug, not a spam or forgery vector. Already tracked as a pre-VPS fast-follow, not a new finding. | open |
| Informational | Audit/Notify | `backend/core/modules/identity/admin_router.py:229-294` | `add_role` publishes `identity.role_changed` (notifying the user); `remove_role` correctly calls `_audit()` but publishes no event at all — a user who loses a role gets no notification while a user who gains one does. Notify-coverage asymmetry, not an audit-trail gap (both actions are properly hash-chain audited). | open |

**Critical/High rollup (feeds Task 14):** 5 findings, all confirmed —
OTP verify-attempts lost-update race (Critical), OTP issue-cooldown race
(High), RBAC `reactivate_user` missing super-admin-target guard (High),
coins `adjust_confirm` audit-orphan / unrecoverable `reason_note` (Critical),
coins `update_rule` zero audit trail (High). None were refuted.

## Part B deferred-items decisions

| # | Item | Decision | Reasoning |
|---|---|---|---|
| 1 | Referral 20/month cap TOCTOU under multiple workers | **Deferred explicitly.** | Safe today: exactly one `worker` (coins) replica in `docker-compose.dev.yml`, events processed serially. `pg_advisory_xact_lock(hashtext('coins_referrer:' \|\| referrer_id))` is the fix, already named in `referrals.py`'s NOTE comment (lines 133-140) — apply it on the "scale coins-worker beyond 1 replica" ticket, not before. A guard comment was added to `referrals.py` pointing back here. |
| 4 | Unused seeded RBAC perms (coins.rules.write/coins.adjust/coins.abuse.review) — admin gates on raw roles, not these perms | **Deferred, harmless.** | The perms exist in the seed data but nothing reads them; `admin_router.py::_require_role` gates on `roles` directly (documented reason: `modules.coins` cannot import `modules.identity`'s `require_permission`, per the import-linter independence contract). No security gap — the raw-role gate is at least as strict. Revisit once a shared, cross-module permission-check helper exists (Sprint-2+ concern, not scoped here). |
