# GATE 1 evidence (D05, 2026-07-10)

Definition of done: fresh clone -> running stack timed <15 min; an insecure
test endpoint fails CI; restore drill executed with real timings; v0.1.0.

## 1. Fresh clone -> running stack: 71 seconds

Executed 2026-07-10 on the Windows dev box (the running dev stack was stopped
first; the drill cloned into a scratch directory and brought the stack up
from the clone).

| step | measured |
|---|---|
| `git clone` (local remote) | 2 s |
| `pnpm install --frozen-lockfile` | 24 s |
| `docker compose -f docker-compose.dev.yml up -d --build` → `/health` 200 | 45 s |
| **total** | **71 s** |

Caveats, honestly stated: docker base images/layers and the pnpm store were
warm (same machine), and the postgres volume already held migrated data. A
cold machine additionally pays image pulls and `alembic upgrade` — still
comfortably inside 15 minutes on any sane connection. A web app dev server
(`pnpm --filter @agri/web-agri dev`) was separately observed serving pages in
~15 s (section 3).

## 2. Insecure endpoint fails CI

`scripts/dump_public_routes.py --check` — the same command CI's
public-routes job runs — with a temporary undeclared `public=True` route
added to main.py:

```text
UNDECLARED public route: /insecure-demo

public-routes gate FAILED. If this exposure is deliberate, edit
backend/core/public_routes.txt in this PR so the change is visible in review.
exit=1
```

After reverting the route: `public-routes gate OK — 3 declared public
route(s)`, exit 0. (Undeclared-private is also impossible: SecureRouter
injects the 401 auth dependency on registration; see ADR-0009.)

## 3. request-id trace (app -> API -> log)

`/demo/trace` on web-agri (port 3002) sent request id
`9b2e453a-8d2d-4f44-8903-9b8fd03a359d` via `apiFetch` and rendered
"HTTP 200 — x-request-id echoed by API". The API's JSON access line, from
`docker compose -f docker-compose.dev.yml logs api`:

```text
{"ts": "2026-07-10T09:50:11.420+00:00", "level": "INFO", "logger": "agri.access", "msg": "request", "request_id": "9b2e453a-8d2d-4f44-8903-9b8fd03a359d", "method": "GET", "path": "/health", "route": "/health", "status": 200, "duration_ms": 1.7}
```

## 4. PII redaction sample (live container)

```text
input:  get_logger('demo').info('farmer +91 98765 43210 (ravi.kumar@example.co.in) signed up')
output: {"ts": "2026-07-10T09:50:33.937+00:00", "level": "INFO", "logger": "demo", "msg": "farmer [REDACTED] ([REDACTED]) signed up", "request_id": null}
```

The unit suite (tests/test_telemetry.py) pins this behaviour, including the
counter-case found live: digit runs inside UUIDs are NOT redacted, so request
ids stay greppable.

## 5. Restore drill

Executed (not simulated) against the local Docker Postgres: total RTO **3 s**
for 7 tables / 2,077 rows, dump 76 KB. Full measurements and activation plan:
docs/runbooks/backup-restore.md.

## Known gaps carried into Sprint 1
- Branch protection is convention-only on the free plan
  (docs/runbooks/branch-protection.md "Known Gap") — revisited at this gate
  per D04; still the owner's call, enforcement activates on Team upgrade.
- Kuma, R2 upload, WAL archiving, Sentry DSNs, and Netdata are
  ready-but-inactive until the VPS exists (docs/runbooks/monitoring.md,
  docs/runbooks/backup-restore.md — "ACTIVATE AT LAUNCH PREP").
