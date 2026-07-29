# Load tests (D30.D)

Two k6 scenarios: `browse.js` (500 VU, the anonymous read surface) and
`auth.js` (50 VU, OTP issuance).

```bash
# prerequisites: dev stack up, API on :8000, signup_enabled flag ON
k6 run load/browse.js
k6 run load/auth.js

# against another environment
API_BASE=https://staging.milk.in k6 run load/browse.js
```

## Baseline recorded 2026-07-29 (D30)

Windows workstation, single-process uvicorn (dev mode), Postgres in Docker,
`RATE_LIMIT_REQUESTS=1000000` (see the next section for why that is required).

| | browse (500 VU) | auth (50 VU) |
|---|---|---|
| requests | 10,394 | 2,701 |
| throughput | 97.7 req/s | 38.3 req/s |
| p95 | **13.16s** | **77ms** |
| 5xx / unexpected failures | **0.02%** | **0.00%** |
| correctness checks | 99.97% passed | 100% passed |

**What this establishes:** the application does not start erroring under 500
concurrent browsers — 0.02% failures against a <1% bar — and the D18 reveal
contract holds under load (the "profile leaks no phone" check passed on every
one of ~3,400 vendor-profile responses).

**What it does not establish:** anything about production latency. The 13.16s
p95 is a *single-process dev server* saturating one CPU at 500 VU; it crossed
the 5s smoke-alarm threshold and that is expected on this hardware. It is not
diagnostic and must be re-measured on staging at D31 before anyone treats it as
a number.

**auth is throttle-bound by design.** Only 17 of 2,701 OTP requests were issued;
the rest answered 429. That is the D07 per-IP daily ladder doing its job — all
50 VUs share one source IP, which is precisely the shape of a credential-
stuffing attempt. Read the 99.37% "failure" rate as the defence engaging, not as
breakage: the threshold is scoped to `expected_response:true`, which was 0.00%.

## Why the rate limiter must be raised to measure anything

The first run of `browse.js` returned **86% failures and a 6.5s p95** — and
measured nothing but `shared/security.py`. The app limits 60 requests / 60s per
IP **per path**, k6 runs from one IP, and six pincodes means six buckets. Almost
everything 429'd.

Set `RATE_LIMIT_REQUESTS` high on the API process for load runs:

```bash
RATE_LIMIT_REQUESTS=1000000 OTP_TEST_PEEK=true \
  .venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The limiter has its own unit coverage; conflating it with a capacity test tells
you nothing about either. (That the key includes the path — so the allowance is
per pincode, not per surface — is recorded as audit finding §4.2.)

## Read this before quoting a number

**A local run is a relative baseline, not a production p95.** It runs Next and
uvicorn in dev mode on a developer workstation, against a Postgres in Docker,
sharing a CPU with the browsers and editors that happen to be open. The absolute
latencies mean nothing about production.

What it is genuinely good for, and what it was added for:

- **N+1 queries** — a route whose latency climbs with concurrency while CPU
  stays flat is usually issuing per-row queries.
- **Connection-pool exhaustion** — shows up as a latency cliff at a specific VU
  count, not a gradual curve.
- **Lock contention** on the `covers()` compound keyset under concurrent reads.
- **Regression detection** — the same script on the same machine before and
  after a change is a fair comparison, even when the absolute numbers are not.

Real figures need staging, at D31. The D30 audit records non-negotiable 4 as
**not met** for exactly this reason rather than quoting a local number as if it
validated production.

## Why the thresholds look loose

`http_req_duration: p(95)<5000` is not a target. It is a smoke alarm — a value
that only trips if something is badly wrong, chosen so the script fails on
breakage rather than on the noise of a busy laptop. Tighten it against staging
hardware, where a number is worth defending.

`http_req_failed` is the bar that matters: **under 1%**. Under load the
application must not start erroring, and that assertion holds on any hardware.

## auth.js specifics

- **The `signup_enabled` flag must be ON**, or every request answers
  `503 signup_unavailable` (D30.B) and the run measures the gate rather than the
  auth path. There is an explicit check for that, so it fails loudly rather than
  reporting a fast, meaningless pass.
- **429 is a correct answer.** The OTP throttle ladder is *supposed* to fire
  under 50 concurrent requesters; the failure threshold is scoped to exclude it.
- **Never point this at an environment with `sms_provider=msg91`.** It would
  send thousands of real messages at ₹0.25 each. The mock driver is the only
  safe target.

## browse.js specifics

Traffic is spread across six real Coimbatore pincodes rather than hammering one
— a single pincode would sit in the query cache and measure caching rather than
the database. The vendor-profile leg carries a correctness check that a guest
response contains no phone number, so the D18 reveal contract is asserted under
load and not only in the unit suite.
