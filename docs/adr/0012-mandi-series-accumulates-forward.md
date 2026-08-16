# ADR-0012: The mandi series accumulates forward — historical backfill is impossible

**Status:** Accepted (2026-08-16) · **Reversal cost:** one-way, and not ours to reverse — the data does not exist to be fetched. If data.gov.in ever publishes a historical resource covering 2026, backfilling becomes a normal ingest job against this same schema; nothing here blocks that.

## Context
The A-U2 W2 spec names a `series_30d` sparkline and assumes 90 days of price history can be backfilled at launch. It cannot. Probed against the live API on 2026-08-16:

- Resource `9ef84268-…` ("Current Daily Price of Various Commodities from Various Markets") serves **only the live day**. Date filters on it are silently ignored — `filters[arrival_date]=01/07/2026` returns rows dated 16/08/2026, i.e. the full unfiltered current set, with no error and no warning.
- The per-commodity archive resources stop at 2023.
- No published data.gov.in resource contains May–Aug 2026 mandi prices.
- Scraping the Agmarknet web UI is out of bounds under the project's own sourcing rules.

This was verified by probe, not inferred from documentation.

## Decision
The price series **accumulates forward from the first successful scheduled pull**. There is no backfill, and none is planned. Consequences of that are made explicit in the product rather than hidden:

1. `market.price_rows` has a real start date. Dates before it are **absent, not missing** — the distinction matters because absent is permanent and unexplainable by any later job.
2. Every pull attempt is recorded in `market.ingest_runs` (0041) whether it succeeded, failed, or found zero rows. Without that ledger, a gap in the series can never be attributed to "the mandi was closed", "the job never fired", or "the fetch failed" — and because the source only holds the live day, that attribution can never be recovered afterwards.
3. A card never claims history it does not have. The range label states the span actually covered ("since 18 Aug"), not a fixed "30-day", and the sparkline draws no line until a second real observation exists.
4. Because each un-pulled day is permanently lost, the daily pull is treated as a data-integrity job, not a convenience: it runs on a schedule (`mandi-cron`, docker-compose), retries within the day, and records every outcome.

## Consequences
- The sparkline is empty on day one and thin for the first weeks. This is correct, not a defect to be papered over with interpolation, a flat line at today's price, or a placeholder tick.
- The value of the feature grows only with elapsed calendar time. There is no engineering effort that shortens that; the only lever is starting the accumulation earlier.
- Every day between this decision and the first scheduled pull in a persistent environment is a permanently absent day. That cost is silent and compounds daily, which is exactly why it is written down here.
- Revisit only if data.gov.in publishes a historical resource covering 2026, or if a licensed commercial feed is bought. Neither is currently in scope.
