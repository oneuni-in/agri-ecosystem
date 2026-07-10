# Architecture Decision Records

One ADR per Constitution decision (SPEC D05-G). Every ADR states its reversal
cost as a **one-way or two-way door** — the cost of changing course, which is
the number that actually matters when revisiting a decision.

| # | decision | door |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith (one FastAPI deployable) | two-way |
| [0002](0002-agriid-single-sso.md) | AgriID single SSO across all apps | one-way |
| [0003](0003-uuidv7-ids.md) | UUIDv7 for every ID | one-way |
| [0004](0004-cursor-pagination.md) | Cursor pagination only, OFFSET banned | two-way pre-launch |
| [0005](0005-jsonb-i18n.md) | JSONB columns for i18n content | two-way |
| [0006](0006-slug-immutability.md) | Immutable slugs + 301 redirects | one-way |
| [0007](0007-meilisearch.md) | Meilisearch for search | two-way |
| [0008](0008-redis-streams-event-bus.md) | Redis Streams event bus | two-way |
| [0009](0009-secure-router-default-private.md) | SecureRouter: private by default | one-way as policy |
| [0010](0010-lighthouse-ci-gate.md) | Lighthouse CI merge gate | one-way as policy |
| [0011](0011-netdata-kuma-not-prometheus.md) | Netdata + Kuma, not Prometheus/Grafana | two-way |

## Template for new ADRs

```markdown
# ADR-NNNN: <title>

**Status:** Accepted (YYYY-MM-DD) · **Reversal cost:** <one-way|two-way> door — <why>

## Context
<2-5 sentences>

## Decision
<2-5 sentences, referencing the enforcing code/gate>

## Consequences
<bullets: what we gain, what we give up, what would trigger revisiting>
```
