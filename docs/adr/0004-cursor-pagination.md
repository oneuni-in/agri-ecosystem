# ADR-0004: Cursor pagination only — OFFSET is banned

**Status:** Accepted (2026-07-10) · **Reversal cost:** two-way door pre-launch, one-way after — public API consumers bake cursor contracts into their clients; changing the scheme after launch breaks them.

## Context
Directory, leads, and content lists will be browsed deep (SEO landing pages, crawlers). `OFFSET n` reads and discards n rows — O(n) per page — and produces duplicate/skipped rows under concurrent writes. Every list in the constitution is cursor-paginated.

## Decision
All list endpoints paginate by cursor (`shared/pagination.py`: opaque cursor over the UUIDv7 ordering from ADR-0003). A D03 test gate bans `OFFSET` in query code, so a future session cannot quietly regress to it.

## Consequences
- O(1) page fetches at any depth; stable pages under writes.
- No "jump to page 47" UX — deep random access needs a different affordance (filters, search), which is the right UX here anyway.
- Slightly more complex endpoint code, absorbed once in the shared helper.
- Revisit only for admin-internal tooling where OFFSET convenience might justify an explicit, documented exception.
