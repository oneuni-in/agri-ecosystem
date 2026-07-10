# Runbook: monitoring & error tracking (READY BUT INACTIVE)

Everything here is wired but dormant. **ACTIVATE AT LAUNCH PREP** — nothing
below runs until the VPS exists (docs/runbooks/staging-deploy.md).

## Uptime Kuma
Bring-up (VPS): `docker compose -f docker-compose.monitoring.yml up -d`,
open :3011, create the admin account, then add monitors:

| monitor | type | interval | retries | notes |
|---|---|---|---|---|
| API /health | HTTP 200 | 60s | 1 | primary pager |
| API /health/deep | HTTP 200 | 300s | 3 | retries absorb dependency blips — alert-fatigue guard |
| each app / (5 URLs) | HTTP 200 + keyword | 60s | 2 | staging ports 3100–3104, API 8100 |

Alert channel: email to r.aarun9597@gmail.com (SMTP notification with a Gmail
app password) + optional ntfy push to phone. Alert only on confirmed-down
(after retries) — no flapping notifications. Only these monitors: every alert
must be actionable (threat model: alert fatigue).

## Netdata (host metrics, VPS)
Install via the official kickstart script at launch prep. The API exposes
Prometheus-format app metrics at `GET /metrics`:
- p95 latency: derive from the `http_request_duration_seconds` histogram
- error rate: `http_request_errors_total` / `http_requests_total`

Netdata's Prometheus collector scrapes `http://localhost:8100/metrics` on the
staging host. Swap path to a full Prometheus+Grafana stack: ADR-0011 (the
endpoint already speaks the exposition format; zero app changes).

## Sentry
Code is fully wired, inactive without env:
- **Backend:** set `SENTRY_DSN` (+ optional `SENTRY_TRACES_SAMPLE_RATE`);
  release comes from `RELEASE` (git sha baked in via the `GIT_SHA` build-arg
  in deploy-staging.yml).
- **Apps, server side:** set `SENTRY_DSN` in the app containers' environment.
- **Apps, browser side:** `NEXT_PUBLIC_SENTRY_DSN` is inlined at **image
  build time** — setting it at runtime does nothing. To activate, add a
  `NEXT_PUBLIC_SENTRY_DSN` build-arg to the apps' build-push step in
  deploy-staging.yml and an `ARG`/`ENV` pair in apps/Dockerfile's builder
  stage. Without it the client bundle carries only a ~120-byte guard stub and
  zero SDK bytes (verified against the D04 Lighthouse gate).
- **Source maps:** create the Sentry org + 6 projects (`agri-api`,
  `agri-web-agri`, `agri-web-milk`, `agri-web-organic`, `agri-web-id`,
  `agri-web-admin` — the web project names are hardcoded in each app's
  next.config.ts), set repo secrets `SENTRY_AUTH_TOKEN` + `SENTRY_ORG`, and
  flip `"@sentry/cli": false` to `true` in pnpm-workspace.yaml allowBuilds
  (its postinstall downloads the upload binary).

## Activation checklist (launch prep, in order)
1. VPS up + staging deployed (docs/runbooks/staging-deploy.md).
2. Kuma up + monitors + email/ntfy channel; test one forced failure.
3. Netdata installed; confirm it scrapes /metrics.
4. Sentry DSNs in staging env (server) and build-args (browser); verify one
   thrown error arrives tagged with the right release sha; then enable
   source-map upload (secrets + allowBuilds).
5. Backups: docs/runbooks/backup-restore.md activation section.
