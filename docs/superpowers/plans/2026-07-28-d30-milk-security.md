# D30 — Security Freeze + DLT Verify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adversarially audit the whole Milk.in surface, fix every Critical/High, and make launching real signup on the mock SMS driver structurally impossible.

**Architecture:** A two-layer signup gate (a liftable `signup_enabled` flag plus a hard `app_env=="prod" and sms_provider=="mock"` refusal) lands first, because it is the launch-blocking deliverable. The audit then works the surface area by area, each area producing a section of `docs/security/milk-audit.md` plus a regression test for every finding that admits one. Cloudflare and k6 produce artifacts D31 consumes.

**Tech Stack:** FastAPI + SQLAlchemy async, Python 3.13, pytest, Next.js App Router, k6, Redis, Postgres 16.

## Global Constraints

- **Branch:** `feat/d30-milk-security`. PR targets `dev`, never `main`. PR title `feat(d30): milk security freeze`.
- **DO NOT** (from the spec): no launch on mock OTP · no unclosed High findings · **no gate soft-disable**.
- **Non-negotiables 3 and 4 will not be met at D30 close** (WAF not live, k6 not production). They are recorded as deferred-with-reason with the D31 dependency named — never marked done.
- **The signup gate must default OPEN in dev and test.** D29's `e2e-auth` and `e2e-matrix` both drive real OTP login; a gate defaulting closed breaks 15+ specs. The guard keys on `app_env == "prod"` only.
- `modules.directory` must never import `modules.identity` (import-linter). Role-gate, don't permission-gate, inside directory.
- Every new public route must be declared in `backend/core/public_routes.txt` or the `public-routes` CI job fails.
- Migrations need a NOTES block and must pass `scripts/migrate_check.py` (up/down/up).
- Tokens only — no raw hex (`pnpm run check:hex`).
- Conventional commits on every commit subject.

## Prerequisites

```bash
# dev stack up; postgres on 55432 (see docker-compose.dev.yml)
docker start agri-dev-postgres-1 agri-dev-redis-1 agri-dev-minio-1 agri-dev-meilisearch-1
# the dockerised API must NOT hold :8000 during e2e (it lacks OTP_TEST_PEEK)
docker stop agri-dev-api-1
```

k6 is **not installed**. Task 9 installs it (`winget install k6 --source winget`).

## File Structure

**Created:**
- `backend/core/alembic/versions/0028_signup_gate.py` — seeds the `signup_enabled` flag
- `backend/core/modules/identity/signup_gate.py` — the two-layer gate, one responsibility
- `backend/core/tests/test_signup_gate.py` — both layers, including the invariant
- `docs/security/milk-audit.md` — the D30 deliverable
- `docs/runbooks/dlt-registration.md` — what to register, so the clock can start
- `docs/runbooks/cloudflare.md` — edge rules, applied at D31
- `load/browse.js`, `load/auth.js`, `load/README.md` — k6

**Modified:**
- `backend/core/modules/identity/router.py:89` — gate `/auth/otp/request`
- `apps/web-id/…/login` — render the "login coming shortly" notice
- Whatever the audit finds.

---

### Task 1: The signup gate

**Files:**
- Create: `backend/core/modules/identity/signup_gate.py`
- Create: `backend/core/tests/test_signup_gate.py`
- Create: `backend/core/alembic/versions/0028_signup_gate.py`
- Modify: `backend/core/modules/identity/router.py:89-103`

**Interfaces:**
- Produces: `async def signup_allowed(session: AsyncSession | None = None) -> bool` and `class SignupGated(Exception)` with attribute `reason: Literal["flag", "mock_driver_in_prod"]`.
- Produces: HTTP `503` with body `{"detail": "signup_unavailable"}` from `/auth/otp/request` when gated — Task 2's UI keys off that exact string.

**Context:** `flag_enabled(key, *, session=None)` lives in `shared/flags.py:31` with a 30s cache and **fails closed for unknown keys** — so the flag must be seeded by migration or every request is refused. Precedent flags `billing_enabled` / `ads_enabled` are seeded in `0003_feature_flags.py`. `app_env` is `Literal["dev","test","prod"]` (`settings.py:12`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/core/tests/test_signup_gate.py
"""D30.B: signup is gated until DLT clears. Two layers - a liftable flag, and
an invariant that prod can never run signup on the mock SMS driver."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.signup_gate import signup_allowed
from settings import get_settings
from shared.flags import FeatureFlag, reset_flag_cache


async def _set_flag(session: AsyncSession, enabled: bool) -> None:
    session.add(FeatureFlag(key="signup_enabled", enabled=enabled, description="d30"))
    await session.flush()
    reset_flag_cache()


async def test_open_when_flag_enabled_in_dev(db_session: AsyncSession) -> None:
    await _set_flag(db_session, True)
    assert await signup_allowed(session=db_session) is True


async def test_closed_when_flag_disabled(db_session: AsyncSession) -> None:
    await _set_flag(db_session, False)
    assert await signup_allowed(session=db_session) is False


async def test_prod_on_mock_driver_refuses_even_with_flag_on(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The invariant that matters: someone flips the flag in prod before DLT
    clears and real users would receive nothing. Refuse regardless."""
    await _set_flag(db_session, True)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SMS_PROVIDER", "mock")
    get_settings.cache_clear()
    try:
        assert await signup_allowed(session=db_session) is False
    finally:
        get_settings.cache_clear()


async def test_prod_on_msg91_respects_the_flag(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _set_flag(db_session, True)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SMS_PROVIDER", "msg91")
    get_settings.cache_clear()
    try:
        assert await signup_allowed(session=db_session) is True
    finally:
        get_settings.cache_clear()
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_signup_gate.py -q`
Expected: FAIL — `ModuleNotFoundError: modules.identity.signup_gate`.

- [ ] **Step 3: Implement the gate**

```python
# backend/core/modules/identity/signup_gate.py
"""D30.B: the signup gate.

Two layers on purpose. The flag is the control you lift when DLT approval
lands. The prod+mock refusal is an invariant: a flag alone cannot stop someone
enabling signup in production while the mock driver is still configured, which
would silently send nobody anything. The spec's "do NOT launch real signup on
the mock driver" has to be structural, not a matter of remembering.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from settings import get_settings
from shared.flags import flag_enabled

SIGNUP_FLAG = "signup_enabled"


async def signup_allowed(session: AsyncSession | None = None) -> bool:
    settings = get_settings()
    # Invariant first: it cannot be overridden by the flag.
    if settings.app_env == "prod" and settings.sms_provider == "mock":
        return False
    return await flag_enabled(SIGNUP_FLAG, session=session)
```

- [ ] **Step 4: Run and watch it pass**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_signup_gate.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 5: Seed the flag — enabled, because unknown flags fail closed**

```python
# backend/core/alembic/versions/0028_signup_gate.py
"""signup gate flag (D30.B)

NOTES
-----
Seeded ENABLED. shared/flags.py fails closed on unknown keys, so an absent row
would refuse every OTP request including dev and CI, breaking the D29 e2e
suites. Production flips it to false at launch until DLT approval lands; the
prod+mock invariant in modules/identity/signup_gate.py refuses regardless of
this value, so an enabled flag can never by itself put signup live on mock SMS.

Reversible: downgrade deletes the row.
"""
```

Follow the exact revision/down_revision idiom of `0027_push_channel.py`; `down_revision = "0027"`.

- [ ] **Step 6: Verify the migration is reversible**

Run: `cd backend/core && .venv/Scripts/python.exe scripts/migrate_check.py`
Expected: up/down/up clean. **This wipes dev data** — re-run `scripts/load_geo.py` and `scripts/seed_e2e_milk.py` afterwards.

- [ ] **Step 7: Gate the route**

In `router.py`, at the top of `request_otp` (before `issue_otp`):

```python
    if not await signup_allowed(session=session):
        # 503, not 403: this is "temporarily unavailable", and it must not read
        # as an auth failure to a client or a monitor.
        raise HTTPException(status_code=503, detail="signup_unavailable")
```

- [ ] **Step 8: Add an endpoint test proving the route refuses**

Extend `tests/test_otp_endpoints.py` with a test that disables the flag, POSTs `/auth/otp/request`, and asserts `503` + `{"detail": "signup_unavailable"}`. Use the existing `api` fixture (`test_otp_endpoints.py:30`).

- [ ] **Step 9: Whole backend suite must stay green**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest -q -m "not slow"`
Expected: PASS. Failures here mean the gate is refusing in `test` — the guard must key on `prod` only.

- [ ] **Step 10: Commit**

```bash
git add backend/core/modules/identity/signup_gate.py backend/core/tests/test_signup_gate.py backend/core/alembic/versions/0028_signup_gate.py backend/core/modules/identity/router.py backend/core/tests/test_otp_endpoints.py
git commit -m "feat(d30): gate signup behind a flag and a prod-on-mock invariant"
```

---

### Task 2: "Login coming shortly" in web-id

**Files:**
- Modify: the web-id login island (find with `grep -rln "send otp" apps/web-id --include=*.tsx -i`)

**Interfaces:**
- Consumes: `503 {"detail": "signup_unavailable"}` from Task 1.

- [ ] **Step 1: Find the submit handler and read its error branch**

Run: `grep -rn "otp/request\|sendOtp" apps/web-id --include=*.tsx`

- [ ] **Step 2: Handle 503 distinctly**

The existing branch renders a generic error. Add, before it:

```tsx
if (res.status === 503) {
  const body = (await res.json().catch(() => null)) as { detail?: string } | null;
  if (body?.detail === "signup_unavailable") {
    setGated(true); // renders the notice instead of the form
    return;
  }
}
```

Render a calm notice — heading plus one line, design-system tokens only, no raw hex. Copy: **"Login coming shortly."** and "We're finishing SMS verification with our provider. The rest of Milk.in works without an account."

- [ ] **Step 3: Verify manually against a gated backend**

```bash
cd backend/core && .venv/Scripts/python.exe -c "
import asyncio
from sqlalchemy import update
from shared.db import get_sessionmaker
from shared.flags import FeatureFlag
async def m():
    sm=get_sessionmaker()
    async with sm() as s:
        await s.execute(update(FeatureFlag).where(FeatureFlag.key=='signup_enabled').values(enabled=False)); await s.commit()
asyncio.run(m())"
```
Load the login page, request a code, confirm the notice renders and no raw error appears. **Then re-enable it** (same snippet, `enabled=True`) or every later task's e2e run fails.

- [ ] **Step 4: Typecheck, lint, hex**

Run: `pnpm run typecheck && pnpm run lint && pnpm run check:hex`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/web-id
git commit -m "feat(d30): render a login-coming-shortly notice when signup is gated"
```

---

### Task 3: DLT registration runbook

**Files:**
- Create: `docs/runbooks/dlt-registration.md`

**This is the critical-path artifact.** DLT approval is measured in days to weeks and nothing in this repo can shorten it. The runbook exists so the clock starts today.

- [ ] **Step 1: Read the driver to get the template slots exactly right**

Run: `sed -n '55,110p' backend/core/modules/identity/otp_drivers.py`
The three purpose slots are `msg91_template_login`, `msg91_template_verify_email`, `msg91_template_sensitive_action` (`settings.py:77-79`).

- [ ] **Step 2: Write the runbook**

Cover: what DLT is and who registers (principal entity on a telecom operator portal); header/sender-ID registration and its 6-character constraint; one content template **per purpose** with the variable placeholders matching what `MSG91Driver` sends; the four secrets to provision (`MSG91_AUTH_KEY`, `MSG91_SENDER_ID`, and the three template ids) and where they go (`secrets/staging.sops.env` pattern); the switch (`SMS_PROVIDER=msg91`), which also mounts the delivery webhook and therefore **requires a `public_routes.txt` edit** (`router.py:8-11`); and the verification procedure for D31.

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/dlt-registration.md
git commit -m "docs(d30): DLT registration runbook so the approval clock can start"
```

---

### Task 4: Audit — auth, session, and contact reveal

**Files:**
- Create: `docs/security/milk-audit.md` (sections 1–2)

**Format:** follow `docs/security/sprint2-audit.md` — numbered areas, then a severity roll-up, then explicit fix-vs-defer. Read its first 40 lines before writing so the shape matches.

- [ ] **Step 1: Enumerate the real public surface**

```bash
cd backend/core && cat public_routes.txt
.venv/Scripts/python.exe scripts/dump_public_routes.py --check
```
Every entry gets a line in the audit saying why it is public. An entry nobody can justify is a finding.

- [ ] **Step 2: Probe auth**

Specific hypotheses, each answered yes/no with a file:line:
- Can an `otp_proof` be replayed? (`otp_service.consume_otp_proof`)
- Is it purpose-bound — can a `verify_email` proof mint a login session?
- Does `/auth/otp/verify` leak registered-vs-unknown through status, body, or **timing**?
- Does refresh rotation revoke the whole family on reuse? (D09 invariant)
- Can the silent-SSO denylist be bypassed with a crafted `next=`? (open-redirect check)

- [ ] **Step 3: Probe contact reveal (D18)**

- Does any unauthenticated response contain a phone number? Assert against the real API, not by reading code:
```bash
curl -s http://127.0.0.1:8000/directory/businesses/e2e-milk-vendor | grep -c "9876500023"
```
Expected: `0`.
- Can the daily cap be evaded by rotating `branch_id`, or is it per-user?
- Can `payload.source` be forged by the caller to poison attribution?

- [ ] **Step 4: Write sections 1–2 with severities**

Use the sprint2 severity vocabulary. Every finding: what, where (file:line), impact, and a reproduction.

- [ ] **Step 5: Commit**

```bash
git add docs/security/milk-audit.md
git commit -m "docs(d30): audit sections 1-2, auth/session and contact reveal"
```

---

### Task 5: Audit — vendor dashboard IDOR

**Files:**
- Modify: `docs/security/milk-audit.md` (section 3)
- Create: `backend/core/tests/test_d30_idor.py`

**This is the highest-yield area.** Twelve `business_id`-scoped routes exist; each is an IDOR candidate:

```
router.py:213 PATCH /businesses/{id}          router.py:238 POST .../rename
router.py:263 POST .../branches               router.py:314 PUT  .../coverage
router.py:339 PUT  .../categories             router.py:364 PUT  .../tier-selection
router.py:388 GET  .../tier-selection         router.py:406 GET  .../analytics
catalog_router.py:150 POST .../products       claims_router.py:83  POST .../claim
claims_router.py:143 POST .../verification    admin_router.py:387  POST .../tier
```

- [ ] **Step 1: Write a parametrised cross-tenant test**

Two owners, two businesses. For every route above, owner B attempts owner A's `business_id` and must get 403/404 — never 200, and never a 500 (a 500 is itself a finding: it means the handler reached logic it should not have).

```python
# backend/core/tests/test_d30_idor.py
"""D30.A section 3: no vendor may touch another vendor's business through a
substituted business_id. One case per business_id-scoped route."""

import pytest

WRITE_ROUTES = [
    ("PATCH", "/directory/businesses/{bid}", {"name": "x"}),
    ("POST", "/directory/businesses/{bid}/rename", {"name": "x"}),
    ("PUT", "/directory/businesses/{bid}/coverage", {"pincodes": ["641001"]}),
    ("PUT", "/directory/businesses/{bid}/categories", {"categories": ["dairy-farm"]}),
    ("PUT", "/directory/businesses/{bid}/tier-selection", {"tier": "premium"}),
    ("GET", "/directory/businesses/{bid}/tier-selection", None),
    ("GET", "/directory/businesses/{bid}/analytics", None),
]


@pytest.mark.parametrize("method,path,body", WRITE_ROUTES)
async def test_cross_tenant_access_is_refused(api_two_owners, method, path, body) -> None:
    client, victim_business_id, attacker_headers = api_two_owners
    response = await client.request(
        method, path.format(bid=victim_business_id), json=body, headers=attacker_headers
    )
    assert response.status_code in (403, 404), (
        f"{method} {path} leaked cross-tenant: {response.status_code} {response.text[:200]}"
    )
```

Build the `api_two_owners` fixture on the `api` fixture pattern in `tests/test_otp_endpoints.py:30`, minting two users via `modules.identity.service.create_user` and two businesses via `modules.directory.service.create_business`.

- [ ] **Step 2: Run it — expect real findings**

Run: `cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_d30_idor.py -q`
Any 200 is a **High**. Any 500 is at least a Medium.

- [ ] **Step 3: Fix every High, using the existing helper**

`shared/ownership.py:12` provides `owned_by[T]`. Fix at the ownership check, not by patching the symptom in each handler.

- [ ] **Step 4: Rerun until green, then run the whole suite**

```bash
cd backend/core && .venv/Scripts/python.exe -m pytest tests/test_d30_idor.py -q
.venv/Scripts/python.exe -m pytest -q -m "not slow"
```

- [ ] **Step 5: Write section 3 and commit**

```bash
git add docs/security/milk-audit.md backend/core/tests/test_d30_idor.py backend/core/modules
git commit -m "test(d30): cross-tenant IDOR coverage for every business-scoped route"
```

---

### Task 6: Audit — leads, reviews, claims, and seed data

**Files:**
- Modify: `docs/security/milk-audit.md` (sections 4–5)

- [ ] **Step 1: Probe the leads and needs surface**

- Can `POST /leads/inquiries` (public, `leads_router.py:88`) be used to spam a vendor's inbox? What actually caps it?
- Does the needs fan-out cap (`need_fanout_limit`, 10) bound inbox flooding as `needs_service.py:6-7` claims?
- Can a caller respond to an inquiry that is not theirs? (`/leads/inquiries/{id}/responses`)

- [ ] **Step 2: Probe reviews and claims**

- Is the D18 5-per-week review cap per user, and can it be evaded?
- Claims: the decision route's `FOR UPDATE` + capture-before-commit — can two concurrent approvals both win? Reason about it against the code; if uncertain, write a concurrency test rather than guessing.
- Can a claim on an already-owned business succeed? (`claims.py:54` says no — verify.)

- [ ] **Step 3: Probe seed data**

- What would `seed_import` / the D27 demo import expose if run in prod? List the dev phone numbers it plants (`+919000000023`, `+919000000029`, `+919876500023`).
- Is there anything stopping those scripts running against a prod DATABASE_URL? If not, that is a finding — say so plainly.

- [ ] **Step 4: Write sections 4–5 and commit**

```bash
git add docs/security/milk-audit.md
git commit -m "docs(d30): audit sections 4-5, leads/reviews/claims and seed data"
```

---

### Task 7: Audit — PWA cache, OWASP, integration sweep

**Files:**
- Modify: `docs/security/milk-audit.md` (sections 6–7)

- [ ] **Step 1: Audit the service worker**

Read `apps/web-milk/public/sw.js`. Answer: what goes in the cache, and can anything user-specific land in a cache shared by every session on that device? D28's rule was that the SW must not cache `_next/static`; verify what it actually does with **navigations** (`sw.js:40`) and API responses.

- [ ] **Step 2: Run the integration sweep the spec names**

```bash
cd backend/core
.venv/Scripts/python.exe scripts/dump_public_routes.py --check   # public routes
.venv/Scripts/python.exe scripts/migrate_check.py                # committed-tree/migration
git status --porcelain                                           # committed-tree verify
```
Then hand-review the `app_rt` grant matrix: every table added since D22 must have explicit grants, and no table should carry more than it needs. `sprint2-audit.md:120` has the prior matrix to diff against.

- [ ] **Step 3: OWASP Top 10 pass**

One line per category, each either "N/A because…" or a finding. Do not pad — an honest "not applicable, no XML parsing anywhere" is worth more than invented coverage.

- [ ] **Step 4: Write sections 6–7 and commit**

```bash
git add docs/security/milk-audit.md
git commit -m "docs(d30): audit sections 6-7, PWA cache, OWASP, integration sweep"
```

---

### Task 8: Cloudflare runbook

**Files:**
- Create: `docs/runbooks/cloudflare.md`

**Design constraint:** the app already limits **60 req / 60s per IP per path** (`shared/security.py:96`, `settings.py:44`). Edge limits must be **coarser**, or Cloudflare absorbs traffic the app limiter exists to shape and the per-path signal goes dark.

- [ ] **Step 1: Write concrete rules — paths, thresholds, actions**

- Managed WAF ruleset: on.
- Bot Fight Mode: on.
- Rate limit `/auth/*`: strictest tier, challenge — this is the credential-stuffing surface.
- Rate limit contact-reveal and `covers()`: volumetric, well above the app's 60/60 so the app tier still governs per-user fairness.
- Country challenge: state the criteria for turning it on rather than turning it on blind.

- [ ] **Step 2: Record what cannot be verified yet**

The rules are unapplied until D31 provides an origin. Say so at the top of the file.

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/cloudflare.md
git commit -m "docs(d30): cloudflare edge rules, coarser than the app-tier limiter"
```

---

### Task 9: k6 load test

**Files:**
- Create: `load/browse.js`, `load/auth.js`, `load/README.md`

- [ ] **Step 1: Install k6**

Run: `winget install k6 --source winget` then `k6 version`
Expected: a version prints. If PATH has not refreshed, use the full path as with `gh`.

- [ ] **Step 2: Write the browse scenario (500 VU)**

Hit the read surface a real visitor hits: `/catalog/milk/home/641001`, a vendor profile, `covers()`-backed listing. Thresholds: `http_req_failed` rate < 1%, and record p95 rather than asserting a production number.

- [ ] **Step 3: Write the auth scenario (50 VU)**

`/auth/otp/request` against varied phones. **The signup gate must be enabled** or every request 503s — note that in `load/README.md`.

- [ ] **Step 4: Run both and capture the numbers**

```bash
k6 run load/browse.js
k6 run load/auth.js
```

- [ ] **Step 5: Record results honestly**

In `load/README.md`: the numbers, the hardware, and the caveat that dev-mode Next on a laptop is **a relative baseline, not a production p95**. What it does find: N+1 queries, pool exhaustion, `covers()` keyset lock contention. If it surfaces any of those, they are audit findings — add them.

- [ ] **Step 6: Commit**

```bash
git add load/
git commit -m "test(d30): k6 browse and auth scenarios with a local baseline"
```

---

### Task 10: Severity roll-up, triage, and PR

**Files:**
- Modify: `docs/security/milk-audit.md` (roll-up + fix-vs-defer)

- [ ] **Step 1: Write the severity roll-up**

A table of every finding by severity, mirroring `sprint2-audit.md:423`.

- [ ] **Step 2: Confirm every Critical/High is closed**

The spec's DO-NOT is explicit: **no unclosed High findings**. If one cannot be closed in D30, it is not "deferred" — stop and raise it, because that changes the launch decision.

- [ ] **Step 3: Record the deferred items with reasons**

Three, each naming its dependency:
- **Non-negotiable 3 (WAF live)** — deferred to D31, no origin exists before then.
- **Non-negotiable 4 (k6 in budget)** — local baseline only; real figures need staging at D31.
- **Issue #42** — carried from D29, still due before D32.

Plus the recorded DLT decision: **launch D32 with signup gated**, gate lifts by flipping `signup_enabled` once approval lands.

- [ ] **Step 4: Full local gate run**

```bash
cd backend/core
.venv/Scripts/python.exe -m ruff format --check . && .venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy . && .venv/Scripts/lint-imports.exe
.venv/Scripts/python.exe -m pytest -q -m "not slow"
cd ../.. && pnpm run typecheck && pnpm run lint && pnpm run check:hex
pnpm run e2e
```
Expected: all green. The e2e run is the one that catches a gate defaulting closed.

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin feat/d30-milk-security
gh pr create --base dev --title "feat(d30): milk security freeze" --body-file -
```

The body must state: the findings by severity and that all Criticals/Highs are closed; **the DLT decision and that signup ships gated**; that non-negotiables 3 and 4 are explicitly not met, with their D31 dependency; and that `e2e-matrix` still needs adding as a required check (carried from D29).

- [ ] **Step 6: Confirm CI**

Run: `gh pr checks --watch`
Expected: all green. Never merge to `main`.

---

## Self-Review

**Spec coverage:**

| Spec item | Task |
|---|---|
| A. Adversarial audit — auth, contact reveal | 4 |
| A. — vendor dashboard IDOR | 5 |
| A. — leads/reviews/claims, seed data | 6 |
| A. — PWA cache, OWASP, integration sweep | 7 |
| B. DLT / real SMS — gate, runbook, decision | 1, 2, 3, 10 |
| C. Cloudflare | 8 (applied D31) |
| D. k6 | 9 |
| E. Fix triage — every High closed | 5, 10 |
| DoD: milk-audit.md complete | 4–7, 10 |
| DoD: SMS decision recorded | 10 |
| DoD: PR → dev | 10 |

**Deliberately not pre-written:** the audit tasks state hypotheses and commands rather than expected findings, because inventing findings in advance would be worse than useless. Every probe names the file to read and what answer would constitute a finding.

**Type consistency:** `signup_allowed(session=...)` is defined in Task 1 and consumed in Task 1 Step 7 and Task 9 Step 3. The `503 {"detail": "signup_unavailable"}` contract is produced in Task 1 and consumed in Task 2. `SIGNUP_FLAG = "signup_enabled"` matches the migration key in Task 1 Step 5 and the runbook in Task 3.

**Known risk:** Task 1 Step 6 runs `migrate_check.py`, which **wipes dev data**. The step says so and names the two scripts to re-run — this has bitten before.
