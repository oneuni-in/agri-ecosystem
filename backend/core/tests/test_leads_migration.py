"""D18.B/C migration: contact_reveals is append-only for app_rt (grant-level)
and the lead_* notify templates are seeded in all locales.

Each grant-check gets its own test (mirrors test_coins_migration.py's
test_ledger_update_is_blocked/test_ledger_delete_is_blocked split, not
test_catalog_migration's single-test shape): once a statement fails,
Postgres marks the transaction aborted and every subsequent statement in it
raises regardless of grants, so testing UPDATE-then-DELETE in one test
wouldn't actually prove DELETE is denied by the revoke.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _insert_reveal(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO leads.contact_reveals (id, user_id, business_id, branch_id) "
            "VALUES (gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), "
            "gen_random_uuid())"
        )
    )
    await session.flush()


async def test_app_rt_can_insert_but_not_update_contact_reveals(
    db_session: AsyncSession,
) -> None:
    # db_session connects as app_rt: INSERT allowed, UPDATE revoked
    await _insert_reveal(db_session)
    with pytest.raises(Exception):  # noqa: B017 - InsufficientPrivilege wrapping varies
        await db_session.execute(
            text("UPDATE leads.contact_reveals SET business_id = gen_random_uuid()")
        )


async def test_app_rt_cannot_delete_contact_reveals(db_session: AsyncSession) -> None:
    # db_session connects as app_rt: INSERT allowed, DELETE revoked
    await _insert_reveal(db_session)
    with pytest.raises(Exception):  # noqa: B017 - InsufficientPrivilege wrapping varies
        await db_session.execute(text("DELETE FROM leads.contact_reveals"))


async def test_app_rt_can_insert_and_update_needs(db_session: AsyncSession) -> None:
    # D25: needs are mutable state (status transitions), so app_rt keeps
    # INSERT and UPDATE - unlike the append-only contact_reveals
    await db_session.execute(
        text(
            "INSERT INTO leads.needs (id, from_user_id, pincode, payload) "
            "VALUES (gen_random_uuid(), gen_random_uuid(), '641001', '{}'::jsonb)"
        )
    )
    await db_session.execute(text("UPDATE leads.needs SET status = 'fulfilled'"))


async def test_inquiries_need_id_is_fk_to_needs(db_session: AsyncSession) -> None:
    # D25 fan-out link: a need_id that doesn't exist in leads.needs must be
    # rejected by the FK
    with pytest.raises(Exception):  # noqa: B017 - FK-violation wrapping varies
        await db_session.execute(
            text(
                "INSERT INTO leads.inquiries "
                "(id, type, business_id, payload, pincode, need_id) "
                "VALUES (gen_random_uuid(), 'milk_subscription', gen_random_uuid(), "
                "'{}'::jsonb, '641001', gen_random_uuid())"
            )
        )


async def test_lead_templates_seeded_in_all_locales(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT key, locale FROM notify.templates "
                "WHERE key IN ('lead_received', 'lead_response')"
            )
        )
    ).all()
    seen: dict[str, set[str]] = {}
    for key, locale in rows:
        seen.setdefault(key, set()).add(locale)
    assert seen == {
        "lead_received": {"en", "ta", "hi"},
        "lead_response": {"en", "ta", "hi"},
    }
