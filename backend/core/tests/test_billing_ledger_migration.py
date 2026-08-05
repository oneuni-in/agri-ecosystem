"""M5 Task 9 migration 0034: billing.ad_orders + the append-only billing.
ledger_entries ad-revenue ledger + billing.invoices gaining an ad-order
parent. Mirrors tests/test_coins_migration.py (append-only pattern) and
tests/test_audit_integrity.py (admin_database_url / trigger-fires-for-owner
pattern)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.asyncio

CAMPAIGN_A = uuid.UUID("018f0000-0000-7000-8000-0000000000a1")
BUSINESS_A = uuid.UUID("018f0000-0000-7000-8000-0000000000b1")


async def _insert_order(
    session: AsyncSession, *, campaign_id: uuid.UUID = CAMPAIGN_A, status: str = "created"
) -> None:
    await session.execute(
        text(
            "INSERT INTO billing.ad_orders "
            "(id, campaign_id, business_id, status, subtotal_paise, gst_paise, total_paise, quote) "
            "VALUES (gen_random_uuid(), :c, :b, :s, 100, 18, 118, '{}'::jsonb)"
        ),
        {"c": campaign_id, "b": BUSINESS_A, "s": status},
    )


async def _insert_ledger_entry(
    session: AsyncSession, *, entry_type: str = "ad_charge", amount: int = 118
) -> None:
    await session.execute(
        text(
            "INSERT INTO billing.ledger_entries "
            "(id, entry_type, amount_paise, business_id) "
            "VALUES (gen_random_uuid(), :t, :a, :b)"
        ),
        {"t": entry_type, "a": amount, "b": BUSINESS_A},
    )


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
    assert rows == ["ad_orders", "invoices", "ledger_entries", "payment_events", "subscriptions"]


async def test_ad_orders_columns_exist(db_session: AsyncSession) -> None:
    cols = set(
        (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'billing' AND table_name = 'ad_orders'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert cols == {
        "id",
        "campaign_id",
        "business_id",
        "status",
        "subtotal_paise",
        "gst_paise",
        "total_paise",
        "currency",
        "quote",
        "buyer_gstin",
        "razorpay_plink_id",
        "razorpay_payment_id",
        "created_at",
        "updated_at",
    }


async def test_ledger_entries_columns_exist_no_updated_at(db_session: AsyncSession) -> None:
    cols = set(
        (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'billing' AND table_name = 'ledger_entries'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert cols == {
        "id",
        "entry_type",
        "amount_paise",
        "currency",
        "order_id",
        "campaign_id",
        "business_id",
        "razorpay_payment_id",
        "meta",
        "created_at",
    }
    assert "updated_at" not in cols  # append-only: no updated_at (0013 rule)


async def test_ad_orders_status_check(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_billing_ad_orders_status"):
        await _insert_order(db_session, status="not_a_real_status")
    await db_session.rollback()


async def test_ad_orders_live_order_partial_unique(db_session: AsyncSession) -> None:
    await _insert_order(db_session, status="created")
    with pytest.raises(IntegrityError, match="uq_billing_ad_orders_live"):
        await _insert_order(db_session, status="paid")  # same campaign, still "live"
    await db_session.rollback()


async def test_ad_orders_failed_order_frees_campaign_for_retry(db_session: AsyncSession) -> None:
    await _insert_order(db_session, status="failed")
    await _insert_order(db_session, status="created")  # must not conflict: prior order is terminal
    await db_session.flush()


async def test_ledger_entry_sign_check_rejects_positive_refund(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_billing_ledger_entries_sign"):
        await _insert_ledger_entry(db_session, entry_type="ad_refund", amount=100)
    await db_session.rollback()


async def test_ledger_entry_sign_check_rejects_nonpositive_charge(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_billing_ledger_entries_sign"):
        await _insert_ledger_entry(db_session, entry_type="ad_charge", amount=0)
    await db_session.rollback()


async def test_ledger_entry_sign_check_accepts_valid_rows(db_session: AsyncSession) -> None:
    await _insert_ledger_entry(db_session, entry_type="ad_charge", amount=118)
    await _insert_ledger_entry(db_session, entry_type="ad_refund", amount=-118)
    await db_session.flush()


async def test_ledger_entries_append_only_for_app_rt(db_session: AsyncSession) -> None:
    """db_session connects as app_rt: INSERT works, UPDATE/DELETE are denied
    by grant (0015/0021 precedent) - the grant-level defense-in-depth layer,
    distinct from the trigger tested below via the admin role."""
    await _insert_ledger_entry(db_session)
    await db_session.flush()
    with pytest.raises(ProgrammingError, match="permission denied"):
        await db_session.execute(text("UPDATE billing.ledger_entries SET amount_paise = 1"))
    await db_session.rollback()
    with pytest.raises(ProgrammingError, match="permission denied"):
        await db_session.execute(text("DELETE FROM billing.ledger_entries"))
    await db_session.rollback()


async def test_invoices_parent_check_rejects_both_null(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_billing_invoices_parent"):
        await db_session.execute(
            text("INSERT INTO billing.invoices (id, amount_paise) VALUES (gen_random_uuid(), 100)")
        )
    await db_session.rollback()


async def test_invoices_parent_check_accepts_order_only(db_session: AsyncSession) -> None:
    await _insert_order(db_session)
    order_id = await db_session.scalar(
        text("SELECT id FROM billing.ad_orders WHERE campaign_id = :c"), {"c": CAMPAIGN_A}
    )
    await db_session.execute(
        text(
            "INSERT INTO billing.invoices (id, order_id, amount_paise) "
            "VALUES (gen_random_uuid(), :o, 118)"
        ),
        {"o": order_id},
    )
    await db_session.flush()


async def test_invoice_number_seq_exists(db_session: AsyncSession) -> None:
    rows = (
        (
            await db_session.execute(
                text(
                    "SELECT sequence_name FROM information_schema.sequences "
                    "WHERE sequence_schema = 'billing' AND sequence_name = 'invoice_number_seq'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows == ["invoice_number_seq"]
    # nextval() is non-transactional (sequence advances survive rollback), so
    # this only asserts the sequence is usable - not a specific value.
    value = await db_session.scalar(text("SELECT nextval('billing.invoice_number_seq')"))
    assert isinstance(value, int) and value >= 1


async def test_ledger_trigger_fires_for_owner_role(admin_database_url: str) -> None:
    """The trigger (not just the grant) is the real, role-independent
    guarantee: even the table-owner/admin role - which still HAS UPDATE/
    DELETE grants, unlike app_rt - is blocked by the BEFORE trigger firing
    for every role (0032 idiom, coins.reject_ledger_mutation precedent).

    Everything here runs inside transactions that are always rolled back
    (never committed) on one throwaway connection, so - unlike audit.entries,
    whose trigger does NOT block DELETE (test_audit_integrity.py cleans up
    via a real admin DELETE after commit) - no cleanup step is needed or
    even possible: this trigger blocks DELETE unconditionally, for every
    role, so a real committed row here could never be cleaned up again.
    """
    engine = create_async_engine(admin_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            # UPDATE attempt
            trans = await conn.begin()
            await conn.execute(
                text(
                    "INSERT INTO billing.ledger_entries "
                    "(id, entry_type, amount_paise, business_id) "
                    "VALUES (:id, 'ad_charge', 500, :b)"
                ),
                {"id": uuid.uuid4(), "b": BUSINESS_A},
            )
            with pytest.raises((ProgrammingError, DBAPIError)) as excinfo:
                await conn.execute(text("UPDATE billing.ledger_entries SET amount_paise = 999"))
            assert "append-only" in str(excinfo.value)
            await trans.rollback()

            # DELETE attempt - fresh transaction (the prior one is aborted)
            trans = await conn.begin()
            await conn.execute(
                text(
                    "INSERT INTO billing.ledger_entries "
                    "(id, entry_type, amount_paise, business_id) "
                    "VALUES (:id, 'ad_charge', 500, :b)"
                ),
                {"id": uuid.uuid4(), "b": BUSINESS_A},
            )
            with pytest.raises((ProgrammingError, DBAPIError)) as excinfo:
                await conn.execute(text("DELETE FROM billing.ledger_entries"))
            assert "append-only" in str(excinfo.value)
            await trans.rollback()
    finally:
        await engine.dispose()
