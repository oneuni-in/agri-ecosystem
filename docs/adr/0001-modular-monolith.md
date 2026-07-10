# ADR-0001: Modular monolith (one FastAPI deployable)

**Status:** Accepted (2026-07-10) · **Reversal cost:** two-way door — module boundaries + the event bus mean any module can be extracted into a service later at moderate cost; the import contracts exist precisely to keep this door open.

## Context
The platform is eleven product modules (identity, directory, leads, content, market_data, ads, notify, search, billing, coins, ai) built and operated by one person. Microservices would multiply deploys, networking, and failure modes with zero payoff at this scale; an unstructured monolith would rot into a ball of mud that can never be split.

## Decision
One FastAPI deployable (`backend/core`). Modules live under `modules/*` and are forbidden from importing each other — import-linter contracts in `pyproject.toml` (independence between all eleven modules; `shared` may never import `modules`) run in CI. Cross-module communication goes through the Redis Streams event bus (ADR-0008) or a module's public service interface.

## Consequences
- One process to run, debug, and back up; refactors are grep-able.
- Module isolation is enforced mechanically, not by discipline.
- We give up independent scaling per module — acceptable until a module's load profile diverges wildly.
- Revisit when a single module needs independent scaling or a second team appears; extraction cost is bounded because the seams already exist.
