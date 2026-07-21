"""D20 billing schema: tables, constraints, and the append-only grant on
payment_events (non-negotiable: the raw webhook log cannot be rewritten by
the runtime role)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_billing_tables_exist(db_session: AsyncSession) -> None:
    rows = (
        (
            await db_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'billing' ORDER BY table_name"
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows == ["invoices", "payment_events", "subscriptions"]


async def test_one_live_subscription_per_business(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            "INSERT INTO billing.subscriptions (id, business_id, tier, status) VALUES "
            "(gen_random_uuid(), '018f0000-0000-7000-8000-000000000001', 'growth', 'active')"
        )
    )
    with pytest.raises(IntegrityError) as excinfo:
        await db_session.execute(
            text(
                "INSERT INTO billing.subscriptions (id, business_id, tier, status) VALUES "
                "(gen_random_uuid(), '018f0000-0000-7000-8000-000000000001', 'pro', 'past_due')"
            )
        )
    assert "ix_billing_subscriptions_live_business" in str(excinfo.value)
    await db_session.rollback()


async def test_payment_events_append_only_for_app_rt(db_session: AsyncSession) -> None:
    """db_session connects as app_rt: INSERT works, UPDATE/DELETE are denied
    by grant (0015 precedent)."""
    await db_session.execute(
        text(
            "INSERT INTO billing.payment_events "
            "(id, provider_event_id, event_type, payload, outcome) "
            "VALUES (gen_random_uuid(), 'evt_grant_test', 'ping', '{}'::jsonb, 'ignored')"
        )
    )
    with pytest.raises(ProgrammingError, match="permission denied"):
        await db_session.execute(
            text(
                "UPDATE billing.payment_events SET outcome = 'x' "
                "WHERE provider_event_id = 'evt_grant_test'"
            )
        )
    await db_session.rollback()
    with pytest.raises(ProgrammingError, match="permission denied"):
        await db_session.execute(
            text("DELETE FROM billing.payment_events WHERE provider_event_id = 'evt_grant_test'")
        )
    await db_session.rollback()


async def test_billing_templates_seeded_all_locales(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT key, channel, count(*) FROM notify.templates WHERE key IN "
                "('dunning_payment_failed','dunning_reminder',"
                "'subscription_canceled','subscription_activated') "
                "GROUP BY key, channel"
            )
        )
    ).all()
    # 4 keys x 2 channels, each with en+ta+hi
    assert len(rows) == 8
    assert all(count == 3 for _, _, count in rows)
