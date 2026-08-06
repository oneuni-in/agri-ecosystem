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
    session: AsyncSession,
    *,
    campaign_id: uuid.UUID = CAMPAIGN_A,
    status: str = "created",
    subtotal: int = 100,
    gst: int = 18,
    total: int = 118,
) -> uuid.UUID:
    order_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO billing.ad_orders "
            "(id, campaign_id, business_id, status, subtotal_paise, gst_paise, total_paise, quote) "
            "VALUES (:id, :c, :b, :s, :sub, :g, :t, '{}'::jsonb)"
        ),
        {
            "id": order_id,
            "c": campaign_id,
            "b": BUSINESS_A,
            "s": status,
            "sub": subtotal,
            "g": gst,
            "t": total,
        },
    )
    return order_id


async def _insert_ledger_entry(
    session: AsyncSession,
    *,
    entry_type: str = "ad_charge",
    amount: int = 118,
    order_id: uuid.UUID | None = None,
    meta: str = "{}",
) -> None:
    await session.execute(
        text(
            "INSERT INTO billing.ledger_entries "
            "(id, entry_type, amount_paise, business_id, order_id, meta) "
            "VALUES (gen_random_uuid(), :t, :a, :b, :o, CAST(:m AS jsonb))"
        ),
        {"t": entry_type, "a": amount, "b": BUSINESS_A, "o": order_id, "m": meta},
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
        "razorpay_short_url",
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


async def test_ad_orders_total_must_equal_subtotal_plus_gst(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_billing_ad_orders_total_eq_parts"):
        await _insert_order(db_session, subtotal=100, gst=18, total=200)  # drifted total
    await db_session.rollback()


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


async def test_ledger_entries_one_charge_per_order(db_session: AsyncSession) -> None:
    """DB backstop against a double ad_charge append for the same order
    (money-path review item 5) - e.g. a retried/duplicated Task 10 webhook
    applier bug must not double-charge the ledger even if the application
    code itself has a gap."""
    order_id = await _insert_order(db_session)
    await _insert_ledger_entry(db_session, entry_type="ad_charge", amount=118, order_id=order_id)
    with pytest.raises(IntegrityError, match="uq_billing_ledger_entries_one_charge_per_order"):
        await _insert_ledger_entry(
            db_session, entry_type="ad_charge", amount=118, order_id=order_id
        )
    await db_session.rollback()


async def test_ledger_entries_refund_after_charge_for_same_order_is_fine(
    db_session: AsyncSession,
) -> None:
    order_id = await _insert_order(db_session)
    await _insert_ledger_entry(db_session, entry_type="ad_charge", amount=118, order_id=order_id)
    await _insert_ledger_entry(db_session, entry_type="ad_refund", amount=-118, order_id=order_id)
    await db_session.flush()


async def test_ledger_entries_refund_once_per_refund_id(db_session: AsyncSession) -> None:
    """DB backstop (Task 10 review round 3) against a double ad_refund
    append for the SAME Razorpay refund id - the race backstop behind
    apply_refund_processed's app-level `meta->>'refund_id'` duplicate
    check, for two concurrent deliveries of one rewrapped-retry refund."""
    order_id = await _insert_order(db_session)
    await _insert_ledger_entry(
        db_session,
        entry_type="ad_refund",
        amount=-60,
        order_id=order_id,
        meta='{"refund_id": "rfnd_dup_1"}',
    )
    with pytest.raises(IntegrityError, match="uq_billing_ledger_entries_refund_once"):
        await _insert_ledger_entry(
            db_session,
            entry_type="ad_refund",
            amount=-60,
            order_id=order_id,
            meta='{"refund_id": "rfnd_dup_1"}',
        )
    await db_session.rollback()


async def test_ledger_entries_distinct_refund_ids_both_allowed(db_session: AsyncSession) -> None:
    """The index is scoped on (order_id, refund_id) together - two DISTINCT
    refund ids for the same order (the legitimate split-refund case) must
    both be insertable."""
    order_id = await _insert_order(db_session)
    await _insert_ledger_entry(
        db_session,
        entry_type="ad_refund",
        amount=-60,
        order_id=order_id,
        meta='{"refund_id": "rfnd_split_a"}',
    )
    await _insert_ledger_entry(
        db_session,
        entry_type="ad_refund",
        amount=-58,
        order_id=order_id,
        meta='{"refund_id": "rfnd_split_b"}',
    )
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


async def test_invoice_number_is_unique(db_session: AsyncSession) -> None:
    order_id = await _insert_order(db_session)
    await db_session.execute(
        text(
            "INSERT INTO billing.invoices (id, order_id, amount_paise, invoice_number) "
            "VALUES (gen_random_uuid(), :o, 118, 'INV-0001')"
        ),
        {"o": order_id},
    )
    with pytest.raises(IntegrityError, match="invoice_number"):
        await db_session.execute(
            text(
                "INSERT INTO billing.invoices (id, order_id, amount_paise, invoice_number) "
                "VALUES (gen_random_uuid(), :o, 118, 'INV-0001')"
            ),
            {"o": order_id},
        )
    await db_session.rollback()


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
