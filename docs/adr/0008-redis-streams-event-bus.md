# ADR-0008: Redis Streams event bus

**Status:** Accepted (2026-07-10) · **Reversal cost:** two-way door — the publish/consume API in `shared/events.py` is narrow; swapping the transport (Kafka, Postgres LISTEN/NOTIFY) touches one shared module, not the eleven modules using it.

## Context
Modules are forbidden from importing each other (ADR-0001) but still need to react to each other — a new directory listing must reach search indexing and notifications. Kafka/RabbitMQ are operationally heavy for one box; synchronous HTTP-to-self recreates the coupling the monolith structure forbids.

## Decision
Redis Streams (`shared/events.py`): each interested module consumes through its own consumer group so every group sees every event exactly once; messages exceeding 3 deliveries without an ack move to `<stream>:dlq` for inspection. Redis is already in the stack for caching and rate limiting — zero new infrastructure.

## Consequences
- Durable-enough async fan-out with consumer-group semantics and a dead-letter path, at no added ops cost.
- Redis persistence is weaker than Kafka's — events are operational signals, not the system of record; anything that must survive disaster is in Postgres.
- Revisit when event volume or retention needs outgrow Redis, or when a consumer needs replay-from-history semantics.
