# ADR-0011: Netdata + Uptime Kuma, not a Prometheus/Grafana stack

**Status:** Accepted (2026-07-10) · **Reversal cost:** two-way door, deliberately — `/metrics` already speaks Prometheus exposition format, so the swap is "deploy Prometheus, point it at /metrics, add Grafana" with zero application changes.

## Context
One operator, one VPS (deferred), a handful of services. A Prometheus + Grafana + Alertmanager stack is a part-time job to run well; unwatched dashboards are worse than none. The D05 spec explicitly forbids shipping it now. What's actually needed: is it up (synthetic checks), is the host healthy (system metrics), is the app healthy (p95, error rate), and did something break (Sentry).

## Decision
Right-sized three-piece setup, all ready-but-inactive until the VPS exists (docs/runbooks/monitoring.md): **Uptime Kuma** for synthetic uptime checks + alerting to email/phone; **Netdata** on the VPS for host metrics, scraping the app's own `GET /metrics` (prometheus-client: request counter, 5xx counter, latency histogram for p95); **Sentry** for error tracking with release tags. The app deliberately exposes the *standard* Prometheus format rather than anything bespoke — that is what keeps this a two-way door.

## Consequences
- Near-zero ops: two self-contained tools plus a SaaS, each independently replaceable.
- No long-term metrics retention or dashboard mesh — accepted until there's traffic worth graphing.
- Alert policy: only actionable alerts get channels (threat model: alert fatigue).
- Revisit at >1 service, >1 operator, or when capacity planning needs historical metrics — then execute the swap path above.
