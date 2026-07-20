"""Search module ORM models. There are none: modules/search owns no tables -
it indexes Meilisearch documents built from other modules' fat events
(ADR-0007) and must never read another module's tables directly."""
