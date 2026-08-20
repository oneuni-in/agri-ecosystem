"""D12 non-negotiables 1+2: tampering is DETECTED (not just hashed), and the
runtime role physically cannot UPDATE or DELETE audit rows.

These tests commit real rows (tamper needs a second connection to see them),
so they use their own engines + admin-credential cleanup, not db_session."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from shared.audit import audit, verify_chain
from tests.conftest import audit_trigger_disabled

DAY = date(2020, 6, 15)


def _at(minute: int) -> datetime:
    return datetime(2020, 6, 15, 12, minute, tzinfo=UTC)


@pytest.fixture
async def engines(
    database_url: str, admin_database_url: str
) -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    runtime = create_async_engine(database_url, poolclass=NullPool)
    admin = create_async_engine(admin_database_url, poolclass=NullPool)
    yield runtime, admin
    # app_rt cannot clean audit rows, and since 0054 neither can the owner
    # without disabling the trigger
    async with audit_trigger_disabled(admin), admin.connect() as conn:
        await conn.execute(text("DELETE FROM audit.entries WHERE chain_day = '2020-06-15'"))
        await conn.commit()
    await runtime.dispose()
    await admin.dispose()


async def test_intact_chain_verifies_clean(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    runtime, _ = engines
    async with async_sessionmaker(runtime, expire_on_commit=False)() as session:
        for i in range(3):
            await audit(session, action="test.ok", metadata={"i": i}, now=_at(i))
        await session.commit()
        assert await verify_chain(session, days=[DAY]) == []


async def test_tampered_row_breaks_the_chain(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    runtime, admin = engines
    async with async_sessionmaker(runtime, expire_on_commit=False)() as session:
        for i in range(3):
            await audit(session, action="test.tamper", metadata={"i": i}, now=_at(i))
        await session.commit()
    # a privileged connection (compromised owner creds) rewrites history,
    # which since 0054 means disabling the trigger first
    async with audit_trigger_disabled(admin), admin.connect() as conn:
        await conn.execute(
            text(
                "UPDATE audit.entries SET metadata = '{\"i\": 99}'::jsonb "
                "WHERE chain_day = '2020-06-15' AND seq = 2"
            )
        )
        await conn.commit()
    async with async_sessionmaker(runtime)() as session:
        breaks = await verify_chain(session, days=[DAY])
    assert [(b.day, b.seq, b.reason) for b in breaks] == [(DAY, 2, "hash_mismatch")]


async def test_deleted_row_breaks_the_chain(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    runtime, admin = engines
    async with async_sessionmaker(runtime, expire_on_commit=False)() as session:
        for i in range(3):
            await audit(session, action="test.gap", metadata={"i": i}, now=_at(i))
        await session.commit()
    async with audit_trigger_disabled(admin), admin.connect() as conn:
        await conn.execute(
            text("DELETE FROM audit.entries WHERE chain_day = '2020-06-15' AND seq = 2")
        )
        await conn.commit()
    async with async_sessionmaker(runtime)() as session:
        breaks = await verify_chain(session, days=[DAY])
    assert breaks and breaks[0].reason == "seq_gap"


async def test_app_rt_cannot_update_or_delete(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    runtime, _ = engines
    for statement in (
        "UPDATE audit.entries SET action = 'x' WHERE chain_day = '2020-06-15'",
        "DELETE FROM audit.entries WHERE chain_day = '2020-06-15'",
    ):
        async with runtime.connect() as conn:
            with pytest.raises((ProgrammingError, DBAPIError)) as excinfo:
                await conn.execute(text(statement))
            assert "permission denied" in str(excinfo.value).lower()


async def test_the_owner_cannot_update_or_delete_either(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    """The non-negotiable 0054 adds: grants stop app_rt, but the owner is who
    a compromise of the migration credentials gets you, and every sibling
    ledger (coins, billing, ads, geo) already refuses that. Detection via the
    hash chain is good; refusing the write is better.
    """
    _, admin = engines
    async with async_sessionmaker(admin, expire_on_commit=False)() as session:
        await audit(session, action="test.owner", metadata={"i": 0}, now=_at(0))
        await session.commit()
    for statement in (
        "UPDATE audit.entries SET action = 'x' WHERE chain_day = '2020-06-15'",
        "DELETE FROM audit.entries WHERE chain_day = '2020-06-15'",
    ):
        async with admin.connect() as conn:
            with pytest.raises((ProgrammingError, DBAPIError)) as excinfo:
                await conn.execute(text(statement))
            assert "append-only" in str(excinfo.value).lower()
