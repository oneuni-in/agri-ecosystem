# ADR-0010: Lighthouse CI merge gate

**Status:** Accepted (2026-07-10) · **Reversal cost:** two-way door mechanically (thresholds are config), one-way as policy — lowering thresholds silently is exactly the failure mode the gate exists to prevent; threshold changes require updating this ADR.

## Context
The moat is tens of thousands of programmatic SEO pages; their value collapses if performance or SEO regresses. Performance erodes one "small" PR at a time, and nobody notices until rankings drop. Constitution: all public pages pass Lighthouse 90 in CI.

## Decision
The `lighthouse` job is a required merge check (D04): app home templates must hold perf ≥ 90 / a11y ≥ 95 / seo ≥ 95, asserted on the **median of 3 runs** (shared-runner variance is 15–20 points; never assert a single run). `/demo` carries a user-approved carve-out (perf ≥ 80, SEO exempt — it self-noindexes). `scripts/lhci-affected.mjs` audits affected apps and warms URLs first; `htmlLimitedBots` + a pinned emulated UA work around Next 15's streamed-metadata trap.

## Consequences
- Perf/a11y/SEO regressions surface in the PR that causes them, not in analytics months later.
- CI pays ~3 Lighthouse runs per audited URL — bounded by auditing only affected apps.
- Variance failures must be diagnosed (rerun, warm-up), never "fixed" by lowering thresholds.
- Revisit thresholds only via an explicit edit to this ADR plus lighthouserc.cjs in the same PR.
