# D07 — OTP Service (design + plan)

Spec: docs/Sprint/Sprint1_Spec_Pack_D06-D14_1.md (SPEC D07). Branch feat/d07-otp-service → PR to dev.

## Design decisions

**Storage.** `identity.otp_requests` from migration 0007 already has everything
(code_hash, purpose, expires_at, attempts, ip, device_fingerprint) — no new
migration. A row is "active" iff `expires_at > now()` and `attempts <
OTP_MAX_ATTEMPTS`. Reissue, successful consume, and burn all invalidate by
setting `expires_at = now()`; no consumed/burned columns needed.

**Hashing.** `code_hash = HMAC-SHA256(key=settings.otp_pepper,
msg="{phone}:{purpose}:{code}")` hex. The pepper lives only in the environment,
so a DB dump alone cannot offline-brute the 10^6 code space. Verification uses
`hmac.compare_digest`; when no active row exists we still compare against a
dummy digest so timing is identical for unknown phones (enumeration).

**otp_proof.** `secrets.token_urlsafe(32)`, stored in Redis as
`otp:proof:{sha256(token)}` → JSON `{phone, purpose}` with TTL
`OTP_PROOF_TTL_SECONDS` (600). Single-use via GETDEL in
`consume_otp_proof()` — D08/D09 consume it; no session/JWT here.

**Rate limits** (all constants in `modules/identity/otp_limits.py`):

| limit | constant | value |
|---|---|---|
| code length / TTL / attempts | OTP_CODE_LENGTH / OTP_TTL_SECONDS / OTP_MAX_ATTEMPTS | 6 / 300 / 3 |
| resend cooldown escalation per phone | RESEND_COOLDOWNS_SECONDS | (30, 60, 300) |
| escalation level reset window | RESEND_ESCALATION_RESET_SECONDS | 3600 |
| issues per phone per day | OTP_ISSUES_PER_PHONE_PER_DAY | 5 |
| issues per IP per day | OTP_ISSUES_PER_IP_PER_DAY | 20 |
| issues per device fingerprint per day | OTP_ISSUES_PER_DEVICE_PER_DAY | 20 |
| verify attempts per IP per day | OTP_VERIFIES_PER_IP_PER_DAY | 50 |
| distinct phones per IP before audit alarm | SUSPICIOUS_PHONES_PER_IP | 5 |
| otp_proof TTL | OTP_PROOF_TTL_SECONDS | 600 |

Redis keys (module `otp_throttle.py`, INCR/EXPIRE fixed windows like the D04
RateLimiter): `otp:cd:{phone}` (cooldown, TTL = current step),
`otp:cdlvl:{phone}` (escalation level, TTL = reset window, refreshed on each
issue), `otp:day:phone:{phone}`, `otp:day:ip:{ip}`, `otp:day:dev:{fp}`,
`otp:vday:ip:{ip}` (daily counters, 86400s), `otp:phones:{ip}` (SET of phones
per IP, 86400s). Tests prove boundaries by asserting key TTLs (30→60→300) and
by deleting `otp:cd:`/`otp:cdlvl:` keys to simulate elapse — no sleeps.

**Drivers** (`otp_drivers.py`). `SmsDriver` protocol with `send_otp(phone,
code, purpose)`. `MockDriver` appends to a class-level outbox
(`MockDriver.last_code(phone)` for tests) and, only when `app_env == "dev"`,
writes the code to stdout directly — deliberately not through logging, because
the logging pipeline redacts codes by design. `MSG91Driver` posts via httpx
(transport injectable for tests — no vendor calls), carries per-purpose DLT
template-id slots from settings, and logs send cost per SMS. Selection:
`get_sms_driver()` reads `settings.sms_provider` (`mock` default); msg91 is
unreachable unless the flag is flipped.

**Endpoints** (SecureRouter `otp_router`, prefix `/auth/otp`, both `public=True`,
plus the default per-route rate limit):
- `POST /auth/otp/request` `{phone, purpose, device_fingerprint?}` → always
  `200 {"status": "sent"}` for well-formed phones whether or not the phone is
  registered; throttled → `429` + `Retry-After`. Invalid phone → 422 (format
  check only, no registry lookup).
- `POST /auth/otp/verify` `{phone, purpose, code}` → `200 {otp_proof,
  expires_in}` or `400 {"detail": "invalid_or_expired_code"}` — one identical
  body for wrong code / expired / burned / no code / unknown phone.

**Webhook.** `msg91_webhook_router()` (POST `/auth/otp/webhook/msg91`,
public=True, HMAC-SHA256-of-raw-body signature in `x-msg91-signature`,
`compare_digest`, 401 on mismatch) is mounted by `create_app()` ONLY when
`sms_provider == "msg91"`. Default (mock) builds therefore expose exactly the
two OTP routes — public_routes.txt gains exactly two lines and the CI gate
stays truthful; flipping the flag in prod requires editing public_routes.txt
then, which is the deliberate-exposure review the gate exists for.

**Telemetry (F).** Aggregate Prometheus counters in shared/metrics.py
(`otp_issued_total{purpose,driver}`, `otp_verify_total{result}`,
`otp_send_cost_inr_total`) — phone/IP never become label values (cardinality +
PII). Per-phone/per-IP counting lives in the Redis throttle keys. Audit hooks:
structured `logger.warning` events (`otp_abuse.burst_issues` when the per-phone
daily cap trips, `otp_abuse.many_phones_per_ip` when the per-IP phone set
reaches SUSPICIOUS_PHONES_PER_IP) with counts and IP only — never phones/codes.

**PII filter.** Extend `shared/telemetry.scrub` with a standalone-6-digit-run
pattern (same UUID-protecting lookarounds as the phone regex). Over-redaction
(e.g. pincodes in log text) is acceptable per D05's stated bias.

**Settings.** `sms_provider: Literal["mock","msg91"]="mock"`, `otp_pepper`
(dev default), `msg91_auth_key`, `msg91_sender_id`, `msg91_webhook_secret`,
`msg91_template_login`, `msg91_template_verify_email`,
`msg91_template_sensitive_action`.

**DB dependency.** New `shared.db.get_session` FastAPI dependency (yield
session, commit on success); endpoint tests override it with the rollback
fixture session.

## Task list

1. settings fields + `otp_limits.py`
2. telemetry scrub extension + tests
3. metrics counters (+ reset hook)
4. drivers + tests (mock default, flag flip, msg91 request shape via
   MockTransport, cost logging, no network in tests)
5. throttle + boundary tests (every number: 30/60/300, level reset, 5, 20, 20,
   50, suspicious-set audit)
6. service + tests (happy, reissue-invalidates, expiry, 3-attempt burn,
   purpose scoping, hash at rest, proof single-use)
7. endpoints + tests (enumeration-identical bodies, 429s, proof round trip),
   public_routes.txt + test_main expectations
8. webhook + tests (absent under mock, signature reject/accept)
9. gates: pytest, ruff check+format, mypy, import-linter, public-routes --check
10. line-by-line review of throttle + verify paths (DoD)
11. conventional commits → push → PR `feat(d07): otp service` → dev

## Assumptions carried from spec (flagged in PR)

- MSG91 is the vendor; +91-only at launch (D06 normalize_phone already
  defaults +91 and accepts other E.164 — no further narrowing here).
- DLT filing is a human/owner action — reminder surfaced in PR body, not
  automatable here.
