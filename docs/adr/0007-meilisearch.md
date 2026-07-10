# ADR-0007: Meilisearch for search

**Status:** Accepted (2026-07-10) · **Reversal cost:** two-way door — all indexing and querying goes through the `search` module, so the engine can be swapped behind that interface; indexes are rebuildable from Postgres, the source of truth.

## Context
Directory/content search needs typo tolerance (transliterated Tamil/Hindi terms guarantee misspellings), faceting (vertical × geo × attributes), and sub-50ms responses. Elasticsearch delivers that with a JVM-sized ops burden one operator shouldn't carry; Postgres trigram search hits a relevance ceiling fast.

## Decision
Meilisearch v1.13 (docker-compose service, IPv4 healthcheck per the D01-B trap). Only the `search` module talks to it; other modules publish index-worthy changes over the event bus. Postgres remains authoritative — Meilisearch state is disposable and rebuildable.

## Consequences
- Typo-tolerant, faceted, fast search with a single small binary to operate.
- Weaker query language than ES — acceptable; complex analytics belong in Postgres.
- One more stateful service to monitor (its /health is in the deep healthcheck).
- Revisit if index size or query features outgrow it; the swap is contained to one module.
