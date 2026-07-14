"""D13 migration: coins schema exists, ledger is immutable, rules seeded."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import InternalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _insert_entry(session: AsyncSession, idem: str = "t:1", delta: int = 100) -> None:
    await session.execute(
        text(
            "INSERT INTO coins.ledger_entries (id, user_id, delta, reason_code, "
            "ref_type, ref_id, idempotency_key, created_at) VALUES "
            "(gen_random_uuid(), gen_random_uuid(), :d, 'test', 'test', null, :k, now())"
        ),
        {"d": delta, "k": idem},
    )


async def test_seeded_rules_present(db_session: AsyncSession) -> None:
    codes = set((await db_session.execute(text("SELECT code FROM coins.rules"))).scalars().all())
    assert {
        "signup_complete",
        "profile_100",
        "daily_visit",
        "referral_referrer",
        "referral_referee",
    } <= codes


async def test_ledger_update_is_blocked(db_session: AsyncSession) -> None:
    await _insert_entry(db_session, idem="upd:1")
    await db_session.flush()
    with pytest.raises((InternalError, ProgrammingError)):
        await db_session.execute(text("UPDATE coins.ledger_entries SET delta = 1"))


async def test_ledger_delete_is_blocked(db_session: AsyncSession) -> None:
    await _insert_entry(db_session, idem="del:1")
    await db_session.flush()
    with pytest.raises((InternalError, ProgrammingError)):
        await db_session.execute(text("DELETE FROM coins.ledger_entries"))


async def test_idempotency_key_is_unique(db_session: AsyncSession) -> None:
    await _insert_entry(db_session, idem="dup:1")
    await db_session.flush()
    with pytest.raises(Exception):  # noqa: B017 - unique-violation wrapping varies by driver
        await _insert_entry(db_session, idem="dup:1")
        await db_session.flush()
