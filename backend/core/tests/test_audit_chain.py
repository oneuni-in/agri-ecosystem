"""D12 hash chain: per-UTC-day genesis, prev/entry hash linkage, seq order."""

import hashlib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from shared.audit import audit, compute_entry_hash, genesis_hash

DAY1_NOON = datetime(2020, 1, 1, 12, 0, tzinfo=UTC)
DAY2_NOON = datetime(2020, 1, 2, 12, 0, tzinfo=UTC)


async def test_first_entry_of_day_chains_from_genesis(db_session: AsyncSession) -> None:
    entry = await audit(db_session, action="test.first", now=DAY1_NOON)
    assert entry.chain_day == DAY1_NOON.date()
    assert entry.seq == 1
    assert entry.prev_hash == genesis_hash(DAY1_NOON.date())
    assert entry.prev_hash == hashlib.sha256(b"genesis:2020-01-01").hexdigest()
    assert entry.entry_hash == compute_entry_hash(entry)


async def test_entries_link_and_seq_increments(db_session: AsyncSession) -> None:
    first = await audit(db_session, action="test.a", metadata={"n": 1}, now=DAY1_NOON)
    second = await audit(db_session, action="test.b", metadata={"n": 2}, now=DAY1_NOON)
    assert second.seq == 2
    assert second.prev_hash == first.entry_hash
    assert second.entry_hash != first.entry_hash


async def test_new_day_restarts_the_chain(db_session: AsyncSession) -> None:
    await audit(db_session, action="test.a", now=DAY1_NOON)
    next_day = await audit(db_session, action="test.b", now=DAY2_NOON)
    assert next_day.seq == 1
    assert next_day.prev_hash == genesis_hash(DAY2_NOON.date())


async def test_hash_covers_metadata(db_session: AsyncSession) -> None:
    entry = await audit(db_session, action="test.a", metadata={"k": "v"}, now=DAY1_NOON)
    entry.meta = {"k": "tampered"}
    assert compute_entry_hash(entry) != entry.entry_hash
