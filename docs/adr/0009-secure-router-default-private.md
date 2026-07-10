# ADR-0009: SecureRouter — every route private by default

**Status:** Accepted (2026-07-10) · **Reversal cost:** one-way door as policy (weakening it reopens the exact hole it closes), two-way per route (`public=True` is a one-line, CI-reviewed change).

## Context
The threat model is a future session — human or AI — adding an endpoint and forgetting auth. Conventions don't survive context loss; only mechanisms do. Constitution: endpoints are private, rate-limited, and validated unless explicitly marked public.

## Decision
Every route registers on `SecureRouter` (`shared/security.py`): an auth dependency that 401s unconditionally (until D08-09 lands real auth) plus a rate limit are injected on registration; routes must declare a `response_model` or return annotation or they fail at import. `public=True` is the only bypass, and CI's public-routes gate diffs the live registry against the committed `backend/core/public_routes.txt` — an undeclared public route fails the PR.

## Consequences
- Forgetting auth is impossible by construction; exposure is always a reviewed diff.
- Currently `/health`, `/health/deep`, `/metrics` are the whole public surface.
- Slight friction adding routes (annotations, registry file) — that friction is the feature.
- D08-09 replaces the 401 stub with real auth and nothing else; any other change to this mechanism needs its own ADR.
