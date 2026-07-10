# ADR-0003: UUIDv7 for every ID

**Status:** Accepted (2026-07-10) · **Reversal cost:** one-way door for existing rows — rekeying live data and every foreign key is prohibitive; treated as one-way even though new tables could technically diverge.

## Context
IDs must be generatable anywhere (API, workers, seeds) without coordination, non-enumerable on public URLs, and index-friendly. Serial integers leak volume and invite enumeration; random UUIDv4 shreds b-tree locality at scale.

## Decision
Every primary key is a UUIDv7 (time-ordered, random tail): backend generation via the `uuid6` library, applied by the D03 model mixins; request ids reuse the same shape. The time prefix keeps inserts append-mostly in the index and makes IDs roughly sortable by creation.

## Consequences
- Good index locality, no ID coordination, safe to expose in URLs.
- IDs leak coarse creation time — acceptable for this domain (public listings anyway).
- 16 bytes per key vs 4/8 for integers — fine at this data volume.
- Revisiting would only happen for a new table with an extreme insert rate where even v7 indexing hurts; that table would get its own ADR.
