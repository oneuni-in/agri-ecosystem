# SPRINT 1 SPEC PACK — D06–D14: AGRIID + AGRICOINS
# One spec per fresh Claude session. Every spec: branch off dev → build → PR → dev → merged same day.
# Prereq: v0.1.0 tagged (Sprint 0 complete). All work runs locally in Docker — no VPS needed this sprint.
# ⚠ EXTERNAL CLOCK: DLT SMS registration must be FILED by D10–12 or the D32 launch slips 1:1.
#   Dev is unblocked meanwhile via the mock OTP driver (built D07).
# REVIEW POSTURE: this is the deepest-review sprint. Files marked 🔍 = you read every line before merge.
# GATE 2 (D14): one AgriID signs into all 3 site domains · OTP-abuse suite green · 10k concurrent
# coin awards with zero balance drift → promote dev→main, tag v0.2.0.

═══════════════════════════════════════════════════════════════
## SPEC D06 — IDENTITY SCHEMA (~6h) · branch: feat/d06-identity-schema
═══════════════════════════════════════════════════════════════
CONTEXT: First real module: backend/core/modules/identity. Use the D03 machinery — base mixins
(UUIDv7/UTC/soft-delete), migration template, multi-schema Alembic (schema name: identity).
AgriID model: internal UUID NEVER exposed anywhere (no URL, no API response, no INFO log);
public identity = @handle (user-chosen) or AG-XXXXXXX fallback. One account = one phone number.

DO:
A. Tables (schema identity, via migration template):
   users (phone E.164 unique, phone_verified_at, status ENUM active/suspended/deleted, agri_id unique,
   agri_id_changed_once bool), handles_history, otp_requests (phone, code_hash, purpose, expires_at,
   attempts, ip, device_fingerprint), sessions_refresh (user_id, token_hash, device_label, ip,
   expires_at, revoked_at, rotated_from), emails (user_id, email unique, verified_at),
   roles, permissions, role_permissions, user_roles, profiles (name, avatar_key, state, district,
   pincode, language ENUM en/ta/hi, interests JSONB, completion_score int),
   addresses, preferences (notifications JSONB, privacy JSONB).
B. @handle rules in a pure, unit-tested module: lowercase a–z 0–9 underscore, 4–20 chars,
   reserved-word blocklist (admin, agri, milk, organic, official, support, help, root, api, www,
   aavin, amul + extensible list file), one free change ever (enforced via agri_id_changed_once).
C. AG-XXXXXXX fallback generator: 7-char Crockford base32 from an atomic Postgres sequence,
   collision-impossible by construction, unit-tested.
D. SQLAlchemy models on D03 mixins; identity service layer skeleton (create_user, get_by_phone,
   assign_role) — service interface only, no HTTP yet.
E. Seed migration: roles (user, farmer, business_owner, staff, super_admin) + baseline permissions.
F. Serialization guard: a Pydantic base for identity responses that STRUCTURALLY excludes user.id
   (UUID) and phone from any public schema; test proving a response model containing raw UUID fails.

DO NOT: no HTTP endpoints yet (D07+) · no auth/JWT logic (D08–09) · no profile completion scoring
logic (D11) · phone/email never in any public response model · no cross-module imports.

NON-NEGOTIABLES:
1. Internal UUID and phone are unexposable by construction (guard + test), not by convention.
2. Every migration downgrades cleanly (CI enforces).
3. Handle + fallback generators are pure functions with exhaustive unit tests incl. blocklist.
4. otp_requests stores code HASH only — never plaintext codes.

THREAT MODEL: identity-table leakage (UUID/phone exposure) and handle-squatting of official names —
the blocklist and serialization guard exist for these.
ASSUMPTIONS TO CONFIRM: E.164 with +91 default; interests as JSONB string array.

DEFINITION OF DONE: migrations up+down in CI; all unit tests green; 🔍 you have read every table
definition and the serialization guard line-by-line; PR → dev merged. `feat(d06): identity schema`.

═══════════════════════════════════════════════════════════════
## SPEC D07 — OTP SERVICE (~5.5h) · branch: feat/d07-otp-service
═══════════════════════════════════════════════════════════════
CONTEXT: Phone OTP is THE credential for the whole ecosystem. DLT registration is pending, so the
MOCK DRIVER is primary (logs code to console/test inbox in dev); real SMS vendor driver is built
but disabled behind flag sms_provider=mock|msg91. ⚠ If DLT is still unfiled today: FILE IT — this is
reminder #1; D32 slips one day for every day it's late past ~D12.

DO:
A. OTP issue service: 6-digit code, 5-min TTL, code stored as hash, purpose-scoped (login|verify_email
   |sensitive_action), single active code per phone+purpose (reissue invalidates prior).
B. Verify service: max 3 attempts per code then burn; constant-time hash compare.
C. Rate limits (Redis, tested): resend cooldown 30s→60s→300s escalating per phone;
   max 5 OTP issues per phone per day; per-IP issue cap (20/day) and per-device-fingerprint cap;
   verification attempts per IP capped. All limits as config constants in one file.
D. Driver interface + two drivers: MockDriver (dev/test: logs + exposes last code to tests) and
   MSG91Driver (DLT template ID slots, delivery-status webhook endpoint [public, signature-checked],
   send-cost logging) — selected by settings flag, default mock.
E. Endpoints on SecureRouter: POST /auth/otp/request (public, rate-limited hard) and
   POST /auth/otp/verify (public) — verify returns a short-lived "otp_proof" token consumed by D08/D09
   login flow, NOT a session yet.
F. Abuse telemetry: counters for issues/verifies/failures per phone+IP; audit-log hooks for
   suspicious patterns (burst issues, many phones per IP/device).
G. Test suite: happy path, expiry, attempt-burn, every rate limit boundary, resend escalation reset,
   webhook signature rejection.

DO NOT: no session/JWT issuance here (D09) · no plaintext codes at rest or in logs (PII filter must
also redact codes) · no vendor calls in tests · public endpoints are the ONLY two listed above.

NON-NEGOTIABLES:
1. Every rate-limit boundary has an explicit test (the suite proves the numbers, not the intent).
2. Codes hashed at rest; codes and phones redacted in logs (extend D05 PII filter, test it).
3. Mock driver default; real driver unreachable unless flag flipped.
4. public_routes.txt updated with exactly the two new routes (CI gate will verify).

THREAT MODEL: OTP flooding (SMS cost attack), brute-force verify, enumeration of registered phones
(responses must be identical for known/unknown numbers), SIM-swap (note: sensitive actions later
require re-verification — hook the purpose scoping now).
ASSUMPTIONS TO CONFIRM: MSG91 as intended vendor; +91-only at launch.

DEFINITION OF DONE: full limit-boundary suite green; enumeration test proves identical responses;
🔍 you read the rate-limit and verify logic line-by-line; PR → dev merged. `feat(d07): otp service`.

═══════════════════════════════════════════════════════════════
## SPEC D08 — OAUTH2 + PKCE AUTHORIZATION SERVER (~6h) · branch: feat/d08-oauth-server
═══════════════════════════════════════════════════════════════
CONTEXT: id.agri.in is the SSO brain: OAuth2 Authorization Code + PKCE via authlib (DO NOT hand-roll
protocol crypto). First-party clients only: web-agri, web-milk, web-organic, web-admin. Different
TLDs cannot share cookies — this server is how one login works everywhere. Plan mode first.

DO:
A. authlib AuthorizationServer wiring: GET /authorize (public; requires id.agri.in session — session
   arrival in D09; until then returns login_required redirect), POST /token (public; code exchange,
   PKCE S256 verified, client_id validated against registry).
B. oauth_clients table (seeded: 4 first-party clients w/ exact redirect URIs per environment) +
   oauth_codes (one-time, 60s TTL, PKCE challenge stored, consumed-at).
C. RS256 signing: keypair management (env-provided PEM in dev), kid headers, GET /.well-known/jwks.json
   (public), key-rotation runbook (docs/runbooks/jwks-rotation.md).
D. Access-token claims (issued by /token, full session semantics in D09): sub=user UUID (internal only —
   downstream services see it, browsers get only agri_id in profile responses), agri_id, roles,
   iat/exp (15 min), aud=client_id, iss=id.agri.in.
E. Strict redirect-URI exact matching; state parameter required and round-tripped; error responses per
   RFC (no open-redirect via error paths).
F. Tests: full happy-path code flow with PKCE, wrong verifier rejected, code reuse rejected, expired
   code rejected, redirect-URI mismatch rejected, foreign client_id rejected, JWKS serves valid keys.

DO NOT: no refresh tokens yet (D09) · no consent screen (first-party only; consent framework is a
Phase-2 note) · no implicit/password grants — code+PKCE ONLY · no hand-rolled JWT/crypto anywhere.

NON-NEGOTIABLES:
1. PKCE S256 mandatory for every client, no plain fallback.
2. Authorization codes single-use with proof (reuse test).
3. Redirect URIs exact-match from DB registry — no wildcards, no substring matching.
4. public_routes.txt gains exactly: /authorize, /token, /.well-known/jwks.json.

THREAT MODEL: auth-code interception (PKCE), open redirect (exact matching), token forgery (RS256+JWKS),
malicious client registration (registry is seed-only, no registration endpoint exists).
ASSUMPTIONS TO CONFIRM: 15-min access TTL; dev redirect URIs on localhost ports 3000–3004.

DEFINITION OF DONE: full flow test green end-to-end; all rejection tests green; 🔍 you read the entire
authorize+token path line-by-line; PR → dev merged. `feat(d08): oauth2 pkce server`.

═══════════════════════════════════════════════════════════════
## SPEC D09 — SESSIONS, REFRESH ROTATION, WEB-ID APP (~6.5h) · branch: feat/d09-sessions-webid
═══════════════════════════════════════════════════════════════
CONTEXT: Completes the auth core: id.agri.in browser session (OTP login), rotating refresh tokens,
revocation, and the web-id UI. web-id UI MUST use packages/ui components per docs/design-system.md
(theme-agri): SearchBar-less clean auth screens, PincodeInput-style OTP boxes, CategoryTile language
picker, glass pills — match the mockup's visual language.

DO:
A. Login flow on id.agri.in: phone entry → OTP (consumes D07 otp_proof) → if new user: create account
   (D06 service) + handle picker (suggestions + availability check + skip→AG-fallback) → id.agri.in
   session cookie (httpOnly, Secure, SameSite=Lax, its own domain only) → resume /authorize redirect.
B. Refresh tokens: 30-day, ROTATING (each use issues new + revokes old; reuse of a rotated token =
   revoke whole family + audit event), hashed at rest, device-bound (fingerprint + label), per-client.
   POST /token grant_type=refresh_token wired into D08 server.
C. Revocation: logout (this device), logout-everywhere (all sessions+refresh families), server-side
   session store checks. Suspended user = instant deny at every path.
D. web-id screens (packages/ui, EN/TA/HI, ≥44px, vernacular labels): phone entry, OTP entry
   (auto-advance boxes, resend with visible cooldown countdown), handle picker, language selection,
   active-devices manager (list, label, revoke each, revoke-all).
E. Auth E2E (Playwright): new-user signup, returning login, wrong-OTP lockout UX, device revoke,
   logout-everywhere.

DO NOT: no BFF/app-side cookies yet (D10) · no profile editing beyond handle+language (D11) ·
refresh tokens never readable in plaintext after creation response · no session logic in frontends —
id.agri.in owns the session.

NON-NEGOTIABLES:
1. Refresh reuse-detection revokes the entire token family (test proves it).
2. Cookies httpOnly+Secure; no tokens in localStorage anywhere, ever.
3. Logout-everywhere kills every session and refresh family within one request cycle (test).
4. web-id screens visually consistent with design-system.md (side-by-side check vs mockup language).

THREAT MODEL: refresh-token theft (rotation+family-revoke+device-binding), session fixation
(regenerate on login), XSS token theft (httpOnly, no web storage).
ASSUMPTIONS TO CONFIRM: 30-day refresh TTL; device fingerprint = UA+platform hash (privacy-light).

DEFINITION OF DONE: Playwright suite green; family-revoke test green; 🔍 you read rotation+revocation
logic line-by-line; PR → dev merged. `feat(d09): sessions + web-id`.

═══════════════════════════════════════════════════════════════
## SPEC D10 — SSO WIRING: AUTH-CLIENT SDK + BFF (~5.5h) · branch: feat/d10-sso-wiring
═══════════════════════════════════════════════════════════════
CONTEXT: Make one login work across agri.in / milk.in / organicstore.in (different TLDs). Pattern:
each Next.js app has BFF route handlers doing the OAuth dance server-side; browser gets ONLY that
app's own httpOnly session cookie. packages/auth-client wraps it all.
⚠ DLT reminder #2: if still unfiled, file TODAY — past this point it starts eating launch margin.

DO:
A. packages/auth-client: startLogin() (builds /authorize URL w/ PKCE verifier stored server-side),
   /api/auth/callback route handler (code→token exchange, encrypted session cookie via iron-session
   or equivalent, token refresh handling server-side), /api/auth/logout (local + back-channel to
   id.agri.in), getServerUser() for RSC, useAgriUser() hook (safe client projection: agri_id, name,
   roles, coins_balance placeholder — never UUID/phone).
B. Silent SSO: if id.agri.in session exists, /authorize round-trips without UI — logged-in-on-milk
   means one-click-in on organic. prompt=none handling + graceful fallback to login.
C. Wire into web-agri, web-milk, web-organic, web-admin: Login button → full journey; header shows
   LocationPill/CoinsPill/avatar per design system when authed.
D. Back-channel logout: id.agri.in logout-everywhere notifies clients (signed event) → app sessions
   cleared; plus short app-session TTL w/ silent re-auth as the safety net.
E. Cross-domain E2E (Playwright, local multi-port): login on milk → visit organic → already in →
   logout-everywhere on id → both apps logged out.

DO NOT: no tokens in browser storage or non-httpOnly cookies · no client-side token exchange ·
no shared-cookie hacks across TLDs · admin app additionally requires staff/super_admin role at the
BFF layer (403 otherwise).

NON-NEGOTIABLES:
1. Browser never sees access/refresh tokens — proven by E2E asserting absence in storage+JS-readable cookies.
2. The cross-domain E2E (login once, in everywhere, logout-everywhere kills all) is green.
3. useAgriUser() projection contains no UUID, no phone (type-level + test).
4. web-admin BFF enforces role gate.

THREAT MODEL: token exfiltration via XSS (BFF pattern kills it), CSRF on callback (state+PKCE),
logged-out-but-locally-alive sessions (back-channel + short TTL).
ASSUMPTIONS TO CONFIRM: iron-session (or equivalent) for app cookies; localhost multi-port stands in
for multi-domain in dev (document prod domain config).

DEFINITION OF DONE: cross-domain E2E green; storage-absence assertions green; PR → dev merged.
`feat(d10): sso wiring`.

═══════════════════════════════════════════════════════════════
## SPEC D11 — PROFILES + RBAC (~5.5h) · branch: feat/d11-profiles-rbac
═══════════════════════════════════════════════════════════════
CONTEXT: Progressive profile (works with just a phone; grows over time) + role-based access control
used by every future module. UI via packages/ui on web-id (account section) + a profile-nudge
component apps can embed.

DO:
A. Profile API: PATCH-style progressive updates (name, state/district/pincode via geo validation,
   language, interests, avatar via D03 media-safe upload path); privacy defaults: phone+email never
   public; profile visibility toggles JSONB.
B. Completion score: pure function (phone verified 20 / name 15 / location 25 / language 10 /
   interests 15 / avatar 15), recomputed on update, emits profile.completed event at 100 (coins hook
   consumes it D13).
C. RBAC: require_permission("perm") FastAPI dependency reading roles→permissions (cached, invalidated
   on change); seed permission matrix per role; multi-role users supported.
D. Admin (web-admin): user search (by agri_id/phone-last-4 — never full-phone display), view profile,
   assign/remove roles (audit-logged D12), suspend/reactivate (kills sessions via D09 revocation).
E. UI: account/profile screens on web-id (theme-agri, EN/TA/HI); ProfileNudge component
   ("Complete your profile — 60%") exported from packages/ui.
F. Tests: permission-denied paths per role, score function table-driven, suspension kills access.

DO NOT: no KYC (Phase 2) · no public profile pages yet (per-site later) · no role UI beyond admin ·
suspend ≠ delete (soft-delete only via D03 mixin).

NON-NEGOTIABLES:
1. Every future protected endpoint can express its needs as require_permission — the pattern is proven
   by tests on at least 3 sample permissions.
2. Full phone number never rendered in admin UI (last-4 only) — test.
3. Suspension takes effect within one request cycle everywhere.
4. Score function pure + table-tested; event emitted exactly once per crossing.

THREAT MODEL: privilege escalation (role changes audit-logged, super_admin assignment requires
super_admin), admin as PII-leak surface (last-4 rule), suspended-user zombie sessions.
ASSUMPTIONS TO CONFIRM: score weights above; interests vocabulary free-form v1.

DEFINITION OF DONE: RBAC tests green; admin flows working; nudge component in demo route;
PR → dev merged. `feat(d11): profiles + rbac`.

═══════════════════════════════════════════════════════════════
## SPEC D12 — AUDIT LOG + NOTIFY MODULE (~5.5h) · branch: feat/d12-audit-notify
═══════════════════════════════════════════════════════════════
CONTEXT: Two shared services everything after depends on. Audit = tamper-evident record of sensitive
actions. Notify = one engine for in-app / SMS / email with per-user preferences.

DO:
A. Audit (schema audit): append-only entries (actor_user_id nullable-for-system, action, target_type,
   target_id, metadata JSONB, ip, created_at, prev_hash, entry_hash) — hash chain per day-partition;
   verify_chain() job + tamper test (mutate a row in test → chain breaks); write helper audit(action,...)
   exposed to all modules; wired NOW into: role changes, suspensions, OTP-abuse flags, handle changes.
B. Notify (schema notify): templates (key, channel, locale, body w/ variables), notifications
   (user, template, payload, read_at), deliveries (channel, status, provider_ref, cost);
   channels: in-app (always), SMS (via D07 driver — mock now), email (ZeptoMail driver behind flag,
   mock in dev); per-user channel preferences respected; event-bus consumers so modules emit events,
   not direct sends.
C. In-app notification center UI: bell + unread badge in header (packages/ui), list screen, mark-read;
   wired into all 3 public apps + web-id.
D. Seed templates (en/ta/hi): welcome, login-new-device alert, role-changed, generic-announce.
E. Tests: chain integrity + tamper detection, preference routing (SMS off → in-app only),
   template rendering in 3 locales, delivery-failure retry w/ backoff + dead-letter.

DO NOT: no push notifications yet (PWA push at D28) · no marketing/bulk sends (transactional only) ·
audit rows never updated/deleted — schema-level (no update grant for app role on audit tables).

NON-NEGOTIABLES:
1. Tamper test proves detection (not just hashing).
2. App DB role physically cannot UPDATE/DELETE audit rows.
3. Every notify send passes through preferences — no direct-driver calls from modules (lint contract).
4. All templates exist in all 3 locales or CI fails a completeness check.

THREAT MODEL: audit tampering by a compromised app (DB grants + chain), notification spam as
harassment vector (per-user rate caps), template-variable injection (escape rendering).
ASSUMPTIONS TO CONFIRM: day-partitioned chains; ZeptoMail as email provider.

DEFINITION OF DONE: tamper + preference + locale tests green; bell live in all apps; PR → dev merged.
`feat(d12): audit + notify`.

═══════════════════════════════════════════════════════════════
## SPEC D13 — AGRICOINS LEDGER + RULES + REFERRALS (~7h) · branch: feat/d13-agricoins
═══════════════════════════════════════════════════════════════
CONTEXT: Closed-loop loyalty coins. NOT money: not purchasable, not cashable, not P2P-transferable —
state this in code comments and the coins T&C stub. Architecture: append-only ledger, idempotency
mandatory, balances are derived. This is a 🔍 full-read day.

DO:
A. Ledger (schema coins): entries (user_id, delta int [+earn/−burn], reason_code, ref_type, ref_id,
   idempotency_key UNIQUE, created_at) — append-only (no update/delete grants, like audit);
   balances table = materialized per-user sum updated transactionally with each entry;
   nightly integrity job: recompute vs stored, alert on ANY drift.
B. Services: award(user, rule_code, ref, idem_key) / redeem(user, amount, reason, idem_key)
   [rejects insufficient balance atomically under concurrency] / balance(user) / history(user, cursor).
C. Rules engine: coins.rules table (code, amount, per-user caps daily/weekly/total, active flag,
   valid window) — Sprint-1 active rules: signup_complete 100 (once), profile_100 200 (once),
   daily_visit 5 (1/day); event-bus consumers wire identity/profile events → award with
   deterministic idem keys (e.g., daily_visit:{user}:{yyyy-mm-dd}).
D. Referrals: per-user code, apply-at-signup attribution, referrer 250 + referee 100 on referee
   profile_100 (not on signup — anti-farm), 20/month referrer cap, device-fingerprint + phone-prefix
   clustering flags → abuse queue (admin reviews, can void via COMPENSATING entries only).
E. UI: CoinsPill live balance in all headers; coins history screen (cursor-paginated, reason labels
   localized); admin: rules CRUD (flag-gated), manual adjust (requires reason note + second
   confirmation, audit-logged), abuse queue.
F. Tests: idempotency (same key twice = one entry), concurrency storm (parallel awards + redeems on
   one user → exact final balance, no negative), caps boundaries, referral attribution + caps,
   integrity job detects an injected drift.

DO NOT: no purchase/cash-out/transfer paths — do not even scaffold them · no floating-point anywhere
(integer coins) · corrections ONLY as compensating entries · no direct ledger writes outside the
service (lint contract).

NON-NEGOTIABLES:
1. Same idempotency key can NEVER double-credit — DB-constraint-proven, not app-logic-proven.
2. Concurrency storm test: 10k parallel award/redeem mix → zero drift, zero negative balance.
3. Ledger rows immutable at the DB-grant level.
4. Every award path goes through rules engine caps — no bypass.

THREAT MODEL: double-credit races (constraint), referral farming (delayed reward + caps + clustering),
insider manipulation (manual adjust = dual-confirm + audit + compensating-only), balance drift
(nightly integrity + alert).
ASSUMPTIONS TO CONFIRM: Sprint-1 rule amounts above; monthly referral cap 20.

DEFINITION OF DONE: storm test green at 10k; idempotency + caps + integrity tests green; 🔍 you read
ledger service + rules engine line-by-line; PR → dev merged. `feat(d13): agricoins`.

═══════════════════════════════════════════════════════════════
## SPEC D14 — SPRINT-1 HARDENING + GATE 2 (~6h) · branch: feat/d14-sprint1-hardening
═══════════════════════════════════════════════════════════════
CONTEXT: Adversarial day. Two passes: (1) a fresh Claude session attacks D06–D13 as a security
auditor; (2) fixes land; (3) Gate 2 verification. No new features today.

DO:
A. Adversarial audit session prompt (run it, save findings to docs/security/sprint1-audit.md):
   "You are a hostile security auditor. Attack: OTP flows (flooding, brute force, enumeration,
   race between request/verify), OAuth (code replay, PKCE downgrade, redirect tricks, state omission),
   sessions (rotation races, family-revoke bypass, fixation), RBAC (privilege escalation paths,
   IDOR on profile/admin endpoints), coins (idempotency races, cap bypass via parallel events,
   referral farming, negative-balance paths), audit/notify (chain gaps, spam vectors).
   For each finding: severity, PoC reasoning, fix."
B. Fix every High/Critical; ticket Mediums with rationale if deferred.
C. Rate-limit tune pass: confirm every /auth/* limit fires in tests AND manually via scripted burst.
D. Full-suite runs: auth Playwright E2E, cross-domain SSO E2E, coins storm, chain tamper, PII-redaction.
E. GATE 2 verification checklist executed and recorded in docs/gates/gate2.md:
   □ one AgriID → login on all 3 site domains (localhost multi-port) via SSO
   □ logout-everywhere verified across apps
   □ OTP abuse suite green incl. manual burst
   □ 10k-award storm zero drift
   □ public_routes.txt reviewed by hand — every public route justified in one line each
   □ audit chain verify_chain() clean over sprint's real data
F. Promote: PR dev→main (human), tag v0.2.0.

DO NOT: no new features · no deferring Critical/High findings · do not skip the manual burst test
just because the automated one is green.

NON-NEGOTIABLES:
1. Zero known Critical/High issues at tag time.
2. Gate-2 checklist file committed with every box checked and dated.
3. Audit findings doc committed (including what was fixed how).
4. v0.2.0 tagged from main after human promotion.

THREAT MODEL: this day IS the threat model.
ASSUMPTIONS TO CONFIRM: none — reality wins today.

DEFINITION OF DONE: gate2.md complete · v0.2.0 tagged · you request the Sprint 2 spec pack
(D15–D22: directory, registry/spec-schemas, media, reviews, leads, search, billing[flagged], ads v1,
admin core → GATE 3 → v0.3.0 → then Milk.in build).
