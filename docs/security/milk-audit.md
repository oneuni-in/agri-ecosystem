# Milk.in pre-launch adversarial audit (D30, 2026-07-28)

Branch `feat/d30-milk-security` · Spec: `docs/Sprint/sprint3_D23-D32.md` (D30)
Surface as merged at `bddb6a6` (D29), which is what ships at D32.

Follows the shape of `sprint1-audit.md` / `sprint2-audit.md`: numbered areas,
severity roll-up, then explicit fix-vs-defer.

## How to read a clean result

Most areas below came back clean. That is a real outcome — the ownership,
throttle and moderation machinery from D15–D26 is doing its job — but it is
**evidence about the hypotheses actually tested**, not proof of absence. Each
area therefore lists the specific question asked and how it was answered, so a
later reader can see the gaps rather than inherit false confidence.

Where a negative result could have been produced by a broken test, a positive
control was added (see §3).

---

## 1 — Auth and session

`/auth/otp/request` and `/auth/otp/verify` are the module's only public identity
routes; `public_routes.txt` declares 30 public routes and the `public-routes` CI
gate diffs it against the live registry (verified green).

| Hypothesis | Result |
|---|---|
| An `otp_proof` can be replayed | **No.** `consume_otp_proof` is a Redis `GETDEL` — atomic single-use (`otp_service.py:160`). |
| A `verify_email` / `sensitive_action` proof can mint a login session | **No.** `/auth/login` rejects unless `redeemed[1] == "login"` (`session_router.py:117`). |
| Verify leaks registered-vs-unknown | **No.** Every failure mode returns one 400 body; the enumeration tests in `test_otp_endpoints.py` assert byte-identical responses. |
| Signup can reach production on the mock driver | **No, structurally.** See D30.B: `app_env=="prod" and sms_provider=="mock"` refuses regardless of the `signup_enabled` flag. |

**Not tested:** timing-channel enumeration (response-time differences between
registered and unknown phones). Constant-time behaviour was not measured; the
bodies are identical, the latencies were not compared.

## 2 — Contact reveal (D18)

| Hypothesis | Result |
|---|---|
| The daily cap is evadable by rotating `branch_id` | **No.** The key is `reveal:{user_id}:{YYYYMMDD}` — per user, not per branch (`reveal.py:31`). |
| Redis failure opens the cap | **No.** `RedisError` raises `RevealUnavailableError` → 503. Fail-closed by design; the cap *is* the anti-scraping control. |
| A caller can forge `payload.source == "contact_reveal"` to poison vendor analytics | **No.** Proven empirically: `ContactPayloadIn`/`MilkSubscriptionPayloadIn` declare no `source` field and pydantic v2 defaults to `extra="ignore"`, so a forged key is dropped before persistence. |
| Phone numbers appear in an unauthenticated SSR payload | **No.** Asserted continuously by `e2e/vendor-profile.spec.ts` ("guest sees login-gated contact, never a phone number"). |

## 3 — Vendor dashboard IDOR

The highest-yield area: **eleven** routes take a caller-supplied `business_id`
naming someone else's property. `tests/test_d30_idor.py` drives all eleven with
an attacker principal who owns a business of their own, so a refusal cannot be
explained away as "not a vendor at all".

**All eleven refuse (403/404).**

The second half of that file is the load-bearing part. A mistyped path also
answers 404, so a refusal-only test could pass while exercising routes that do
not exist. A parametrised **positive control** asserts the legitimate owner is
*not* refused on the same URLs. Both halves green means the refusals are authz
decisions rather than routing accidents.

Routes covered: `PATCH /directory/businesses/{id}`, `.../rename`,
`.../branches`, `.../coverage`, `.../categories`, `.../tier-selection` (PUT and
GET), `.../analytics`, `POST /catalog/businesses/{id}/products`,
`GET /leads/inbox`, `GET /leads/inbox/stats`.

### 3.1 — Validation precedes authorisation *(Informational)*

FastAPI validates request bodies before the handler runs, so a non-owner
receives `422` with field-level detail rather than `403`. This leaks request
schema shape, nothing more — the schemas are inferable from the public client
bundle anyway. Framework behaviour; no action.

## 4 — Leads, reviews, claims

| Hypothesis | Result |
|---|---|
| A caller can respond to an inquiry that is not theirs | **No.** `get_owned_inquiry` scopes by owner. |
| Review spam on one business | **No.** One review per user per target (`ReviewExistsError` → 409). The "5/week" figure is a *coins award* cap (`coins.rules.weekly_cap`), not a posting limit. |
| Two concurrent claim approvals can both win | **No.** `claims.py:158` takes `SELECT … FOR UPDATE` on the business, serialising decisions. |
| A claim can succeed on an already-owned business | **No.** `claims.py:54` refuses when `owner_user_id is not None`. |

### 4.1 — Anonymous contact inquiries have no per-business cap *(Medium, deferred)*

`POST /leads/inquiries` is public (`optional_auth`). `business_id` is
caller-supplied and validated only for *coverage*, so an attacker can target one
specific vendor. The only bound is the shared per-IP rate limit — **60 requests
per 60s per path** (`shared/security.py:96`) — and every accepted inquiry
publishes `lead.created`, which becomes an in-app notification to the owner.

That makes vendor-inbox and notification flooding cheap, and trivially unbounded
behind rotating IPs. Note the contrast with neighbouring surfaces: D25 needs
carry `need_post_daily_cap`, reviews are one-per-target. Contact inquiries have
neither.

**Deferred, not closed.** It is abuse/availability, not confidentiality or
integrity, so it is not a High. The proportionate control is the edge tier —
`docs/runbooks/cloudflare.md` specifies a volumetric limit on this path — and a
per-business daily cap risks suppressing genuine demand at launch, which wants
real traffic data before it is tuned. Revisit if abuse appears.

### 4.2 — The app rate limiter is keyed per path, so it does not bound scraping *(Medium, mitigated at the edge)*

`rate_limit()` builds its key as `ratelimit:{client_ip}:{request.url.path}`
(`shared/security.py:154`) — **including the path parameters**. Measured
directly: a burst of 80 requests to one pincode returns exactly 60 × 200 then
20 × 429, and the 61st request to a *different* pincode succeeds immediately.

So the effective allowance is 60/min **per pincode**, not 60/min for the browse
surface. Walking Tamil Nadu's ~10,000 pincodes yields a ~600,000/min budget from
a single IP without ever tripping the limiter. The same applies to
`/directory/businesses/{slug}` — one bucket per business.

This is the correct design for *fairness* (a user browsing many pages is not
punished for it) and it is what the limiter was built for. It is simply not a
scraping control, and should not be mistaken for one.

Discovered while building the D30.D load test, which initially measured the
limiter rather than the application: 86% of requests returned 429 because six
pincodes were being hammered from one IP.

**Mitigation** is the edge tier: `docs/runbooks/cloudflare.md` rule 3.4 applies
a volumetric limit across the whole browse surface, which is the layer that can
see the aggregate a per-path counter cannot. No application change proposed —
tightening the app limiter would penalise genuine browsing to no benefit.

## 5 — Seed and fixture data

### 5.1 — Fixture seeds could write to production *(High — FIXED in this spec)*

No seed script checked `app_env`. A stale `DATABASE_URL`, or an ops shell with
production env loaded, was the only thing between a copy-pasted command and demo
businesses in production.

`seed_e2e_milk.py` is the sharp case: `_ensure_staff()` grants the **`staff`
role** — which gates every admin moderation route in `modules/directory` — to a
fixed phone number, `+919000000029`. That is a plausible-looking allocatable
Indian mobile number. Had the seed run against production, and were that number
held by someone else, they could request an OTP and sign in with staff
privileges.

**Fixed:** `shared/dev_only.py::refuse_in_prod()` aborts before the first write
when `app_env == "prod"`. Applied to exactly the two scripts that fabricate test
state (`seed_e2e_milk.py`, `make_business.py`). `load_geo.py` (geo reference
data) and `import_vendor_seed.py` (the real launch vendor catalogue)
legitimately populate production and are deliberately left unguarded —
`tests/test_dev_only_guard.py` asserts **both** directions, so adding a guard to
those later fails the suite rather than silently breaking a launch task.

The guard lives in `shared/`, not `scripts/`: CI runs
`python scripts/seed_e2e_milk.py` directly, which does not place `scripts` on
`sys.path`, so a scripts-local import would have broken every e2e job.

## 6 — PWA cache (D28)

`apps/web-milk/public/sw.js` is clean. GET-only, same-origin only, and
`/api/*` is explicitly never cached (the PII rule, `sw.js:38`). Navigations are
network-first with an offline-shell fallback and are not stored. The only cached
responses are `/icons/*` — static, no user data. Nothing user-specific can land
in a cache shared across sessions on one device.

## 7 — Integration sweep

- **Public routes:** `dump_public_routes.py --check` green, 30 declared.
- **`app_rt` grants:** every table-creating migration since the D22 audit
  (0023, 0024, 0025, 0027) carries an explicit per-table `GRANT`. 0026 and 0028
  create no tables. No blanket `GRANT ON ALL TABLES` introduced.
- **Committed tree:** clean at audit time.

### 7.1 — Migration 0026 cannot be downgraded once data exists *(Medium, deferred)*

`scripts/migrate_check.py` fails its `downgrade base` leg on a database with
real rows:

```
ForeignKeyViolationError: update or delete on table "categories" violates
foreign key constraint "fk_business_categories_category_id_categories"
on table "business_categories"
```

`0026_dairy_categories.downgrade()` deletes category rows without first clearing
the dependent `business_categories` rows. **CI never catches this** because CI
downgrades an empty database, which is exactly why it survived to launch week.

Operationally this means the documented rollback path does not exist for any
deployment that has assigned a category to a business — i.e. production, from
day one. Not a vulnerability; a recovery-capability gap.

**Deferred** to a migration-focused change rather than a security freeze:
correcting it means either deleting dependents in `downgrade()` or accepting the
migration as irreversible and saying so in its NOTES. Both want the migration
owner's judgement, and neither blocks launch — forward migration is unaffected.

## 8 — OWASP Top 10 (2021)

| # | Category | Finding |
|---|---|---|
| A01 | Broken access control | §3 swept 11 routes + positive control; §5.1 fixed a privilege-seeding path. |
| A02 | Cryptographic failures | Sessions are opaque `Secure`/`httpOnly` cookies; OTP codes are peppered; JWKS asymmetric. No plaintext secrets in the tree (`gitleaks` gate green). |
| A03 | Injection | SQLAlchemy parameter binding throughout; the raw-SQL analytics blocks use bound params. Meili filters go through the D19 allowlist. |
| A04 | Insecure design | The D30.B gate is the deliberate example: an invariant rather than a flag, because the failure it prevents is silent. |
| A05 | Security misconfiguration | §5.1 was exactly this class and is fixed. §7 confirms grants and public routes. |
| A06 | Vulnerable components | `pnpm audit --audit-level high` and `pip-audit` both gate CI. |
| A07 | Auth failures | §1. Throttle ladder + fail-closed reveal cap + enumeration-resistant responses. |
| A08 | Integrity failures | Audit chain is hash-linked (`verify_audit_chain.py`); webhooks are HMAC-verified over the raw body. |
| A09 | Logging failures | Bodies and query strings are never logged in identity; PII scrubbing in `shared/telemetry.py` is the backstop. |
| A10 | SSRF | The D28 push channel carries an allowlist. No user-supplied URL is fetched server-side elsewhere. |

---

## Severity roll-up

| Severity | Count | Items |
|---|---|---|
| Critical | 0 | — |
| High | 1 | §5.1 fixture seeds could write to production — **FIXED** |
| Medium | 3 | §4.1 uncapped anonymous inquiries; §4.2 per-path rate-limit keying does not bound scraping; §7.1 migration 0026 irreversible with data |
| Informational | 1 | §3.1 validation precedes authorisation |

**Zero Critical or High findings remain open**, which is D30's non-negotiable 1.

## Fix vs defer

### Fixed in this spec
- **§5.1** — `refuse_in_prod()` guard + regression test asserting both
  directions.
- **D30.B** — signup gate: `signup_enabled` flag plus the prod-on-mock
  invariant, with the 503 contract rendered as "Login coming shortly".

### Deferred, with reasons
- **§4.1** — proportionate control is the edge tier; a per-business cap wants
  real launch traffic before tuning.
- **§4.2** — mitigated at the edge (Cloudflare rule 3.4) rather than in the
  app; tightening the per-path limiter would punish genuine browsing.
- **§7.1** — belongs to a migration change, needs the owner's call on
  reversible-vs-documented-irreversible.
- **§3.1** — framework behaviour, no action.

### Not met at D30 close — stated rather than marked done
- **Non-negotiable 3 (WAF + rate limits live).** Rules are written in
  `docs/runbooks/cloudflare.md` but **not applied**: the VPS is provisioned at
  D31 and DNS cutover is D32, so no origin exists to put them in front of.
  Applies at D31.
- **Non-negotiable 4 (k6 within budget).** Local baseline recorded
  (`load/README.md`): under 500 concurrent browsers the application does **not**
  start erroring (0.02% failures against a <1% bar) and the D18 reveal contract
  held on every one of ~3,400 profile responses. But the 13.16s p95 is a
  single-process dev server saturating one CPU, not a production figure, so the
  budget half of this non-negotiable is **unmet**. Re-measure on staging at D31.
  The auth scenario is throttle-bound by design — 17 of 2,701 OTP requests
  issued, the rest 429 — which is the D07 per-IP ladder behaving exactly as it
  should against single-source load.
- **Issue #42** — landing-page Lighthouse floor still 0.80 against the
  Constitution's 0.90, carried from D29. Still due before D32.

  New evidence from this spec's CI: **web-milk home scored 0.88 against its
  0.90 floor, then passed on a re-run of the identical commit** (run
  30426975792). D30 changed 31 frontend lines, none of them in web-milk — the
  only thing reaching that page was +183 bytes of i18n JSON, which cannot cost
  two performance points on a 562ms-RTT profile. So the home page now sits close
  enough to its floor that ordinary runner noise tips it under, the same
  headroom problem #42 describes on the landing pages. The threshold was NOT
  lowered; "no gate soft-disable" is on this spec's DO-NOT list, and a gate
  re-baselined every time it flakes stops being a gate. It does mean #42's real
  fix (static/ISR over covered pincodes) buys margin on home as well, and that
  both pages will keep flaking until something buys it.

## The DLT decision (D30.B, non-negotiable 2)

DLT registration **had not been started** when D30 began. Approval is a
third-party queue measured in days to weeks and nothing in this repository can
shorten it, so real SMS cannot be verified before D32.

**Recorded decision: launch D32 with signup gated.** The indexed public surface
— pincode landing pages, directory, vendor profiles, search, category pages —
needs no account and ships on schedule. Signup and login sit behind
"Login coming shortly" until approval lands, at which point the gate lifts by
flipping one flag. Nothing ships on the mock driver: the invariant in
`modules/identity/signup_gate.py` makes that structurally impossible rather than
a matter of remembering.

Registration steps are in `docs/runbooks/dlt-registration.md`. **The clock has
not started; it is the critical path to a complete launch.**
