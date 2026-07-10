# ADR-0005: JSONB columns for translatable content

**Status:** Accepted (2026-07-10) · **Reversal cost:** two-way door — a migration script can pivot JSONB into translation tables if per-language querying or indexing ever dominates.

## Context
Content ships in English, Tamil, and Hindi, with more languages likely. Classic translation tables (one row per entity per language) fan every read out into joins and complicate writes; the read pattern here is "give me this entity in the user's language with fallback".

## Decision
Translatable fields are JSONB columns shaped `{"en": …, "ta": …, "hi": …}` with helpers in `shared/i18n.py` handling fallback. One row per entity; adding a language is a data change, not a migration.

## Consequences
- Single-row reads/writes; language fallback is one dict lookup.
- Full-text search per language happens in Meilisearch (ADR-0007), not Postgres, so JSONB's weaker in-DB text indexing doesn't bite.
- Cross-language consistency (missing translations) is an application concern; the pending-content workflow covers it.
- Revisit if a feature needs relational per-language queries (e.g. "all entities missing Tamil") at scale the JSONB operators can't serve.
