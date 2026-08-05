# backend/core/alembic/versions/0034_billing_ad_orders.py
"""M5 Task 9: billing.ad_orders (one Razorpay Payment Link per checkout
attempt), the append-only billing.ledger_entries ad-revenue ledger, and
billing.invoices gaining an ad-order parent alongside its existing
subscription parent. Also (money-path review fast-follow, same revision -
still unmerged at review time): ad_orders.razorpay_short_url (persist the
hosted checkout link so it survives past the create response), ads.
campaigns.quote (the itemized quote snapshot ads hands billing - see
shared.lookups.CampaignBillingRef.quote), a total=subtotal+gst CHECK on
ad_orders, and a partial-unique backstop on ledger_entries against a
double ad_charge append for one order.

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-05

"""
# -- THREAT/NOTES:
# downgrade data loss: drops billing.ad_orders and billing.ledger_entries
#   in full (every checkout attempt and every ad-revenue ledger row is
#   destroyed - there is no recomputation path, unlike the geo tier CSV
#   precedent in 0032). Also DELETEs every billing.invoices row whose
#   subscription_id IS NULL (ad-order invoices) before subscription_id can
#   be restored to NOT NULL - those invoice rows cannot survive the
#   downgraded schema and are unrecoverable from this migration alone.
#   ads.campaigns.quote is a plain nullable ADD COLUMN/DROP COLUMN - no
#   data-loss note needed beyond "the snapshot itself is gone", same as any
#   other dropped column in this migration.
# locks: three CREATE TABLEs (empty) + one ALTER TABLE billing.invoices
#   (DROP NOT NULL, ADD COLUMN x3, ADD CHECK) + one ADD COLUMN on ads.
#   campaigns (nullable, no rewrite) - ACCESS EXCLUSIVE briefly, all tables
#   are small (D20/M5 volumes). CREATE SEQUENCE is catalog-only.
# rollout: dark behind billing_enabled (D20 kill switch, unchanged by this
#   migration) - modules/billing/router.py's /ad-orders routes 404 while the
#   flag is off, so no live Razorpay traffic depends on this shipping ahead
#   of the flag flip. billing.invoice_number_seq is unused until Task 10
#   wires invoice generation to it. ads.campaigns.quote is populated by
#   modules/ads/selfserve_router.py's create/patch re-quote paths going
#   forward; pre-existing campaigns keep quote=NULL (ads.campaigns already
#   carries the price_paise/price_subtotal_paise/price_gst_paise scalars for
#   those, so nothing is billable-but-unpriced as a result).

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # -- billing.ad_orders ---------------------------------------------
    op.create_table(
        "ad_orders",
        pk_column(),
        sa.Column("campaign_id", _uuid, nullable=False),
        sa.Column("business_id", _uuid, nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="created"),
        sa.Column("subtotal_paise", sa.Integer(), nullable=False),
        sa.Column("gst_paise", sa.Integer(), nullable=False),
        sa.Column("total_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="INR"),
        sa.Column("quote", postgresql.JSONB(), nullable=False),
        sa.Column("buyer_gstin", sa.Text(), nullable=True),
        sa.Column("razorpay_plink_id", sa.Text(), nullable=True, unique=True),
        # the hosted checkout URL itself (Razorpay's `short_url`) - persisted
        # so a poll/refresh after the create response can still show it,
        # rather than dead-ending an abandoned checkout (money-path review).
        sa.Column("razorpay_short_url", sa.Text(), nullable=True),
        sa.Column("razorpay_payment_id", sa.Text(), nullable=True),
        *timestamp_columns(),
        schema="billing",
    )
    # op.f(): final names - without it Base's naming convention re-wraps
    # these and downgrade's drop_constraint cannot find them (M3/0033 trap).
    op.create_check_constraint(
        op.f("ck_billing_ad_orders_status"),
        "ad_orders",
        "status IN ('created', 'paid', 'failed', 'expired', 'refunded')",
        schema="billing",
    )
    op.create_check_constraint(
        op.f("ck_billing_ad_orders_subtotal_nonneg"),
        "ad_orders",
        "subtotal_paise >= 0",
        schema="billing",
    )
    op.create_check_constraint(
        op.f("ck_billing_ad_orders_gst_nonneg"), "ad_orders", "gst_paise >= 0", schema="billing"
    )
    op.create_check_constraint(
        op.f("ck_billing_ad_orders_total_nonneg"),
        "ad_orders",
        "total_paise >= 0",
        schema="billing",
    )
    # money-path review: the three amounts must never drift apart - this is
    # the DB-level backstop against a future code path that sets them
    # inconsistently (create_ad_order itself always derives total from the
    # other two, but the CHECK holds regardless of caller).
    op.create_check_constraint(
        op.f("ck_billing_ad_orders_total_eq_parts"),
        "ad_orders",
        "total_paise = subtotal_paise + gst_paise",
        schema="billing",
    )
    # partial unique: at most one LIVE (created/paid) order per campaign - a
    # failed/expired/refunded order frees the campaign for a fresh checkout.
    op.create_index(
        "uq_billing_ad_orders_live",
        "ad_orders",
        ["campaign_id"],
        unique=True,
        schema="billing",
        postgresql_where=sa.text("status IN ('created', 'paid')"),
    )
    op.create_index(
        "ix_billing_ad_orders_campaign_id", "ad_orders", ["campaign_id"], schema="billing"
    )
    op.create_index(
        "ix_billing_ad_orders_razorpay_payment_id",
        "ad_orders",
        ["razorpay_payment_id"],
        schema="billing",
    )
    # normal CRUD grants (0021 precedent) - status/razorpay_payment_id are
    # updated in place by Task 10's webhook/reconcile, unlike the
    # append-only ledger below.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON billing.ad_orders TO app_rt")

    # -- billing.ledger_entries (append-only ad-revenue ledger) --------
    op.create_table(
        "ledger_entries",
        pk_column(),
        sa.Column("entry_type", sa.Text(), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="INR"),
        sa.Column("order_id", _uuid, sa.ForeignKey("billing.ad_orders.id"), nullable=True),
        sa.Column("campaign_id", _uuid, nullable=True),
        sa.Column("business_id", _uuid, nullable=False),
        sa.Column("razorpay_payment_id", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="billing",
    )
    op.create_check_constraint(
        op.f("ck_billing_ledger_entries_type"),
        "ledger_entries",
        "entry_type IN ('ad_charge', 'ad_refund')",
        schema="billing",
    )
    op.create_check_constraint(
        op.f("ck_billing_ledger_entries_sign"),
        "ledger_entries",
        "(entry_type = 'ad_charge' AND amount_paise > 0)"
        " OR (entry_type = 'ad_refund' AND amount_paise < 0)",
        schema="billing",
    )
    op.create_index(
        "ix_billing_ledger_entries_campaign_id",
        "ledger_entries",
        ["campaign_id"],
        schema="billing",
    )
    op.create_index(
        "ix_billing_ledger_entries_razorpay_payment_id",
        "ledger_entries",
        ["razorpay_payment_id"],
        schema="billing",
    )
    # money-path review: DB backstop against a double ad_charge append for
    # the same order (e.g. a retried/duplicated webhook applier bug in
    # Task 10) - at most one ad_charge row per order_id. ad_refund rows are
    # untouched (a refund can legitimately follow a charge for the same
    # order). Postgres unique indexes treat NULL as distinct from any other
    # value, so rows with order_id IS NULL never collide with each other
    # here regardless.
    op.create_index(
        "uq_billing_ledger_entries_one_charge_per_order",
        "ledger_entries",
        ["order_id"],
        unique=True,
        schema="billing",
        postgresql_where=sa.text("entry_type = 'ad_charge'"),
    )
    # append-only BY GRANT + trigger (0032 idiom: geo.forbid_tier_history_
    # mutation) - a BEFORE trigger fires for every role including the table
    # owner, so it is the real guarantee; the grant is defense-in-depth
    # matching the connecting runtime role (app_rt).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION billing.forbid_ledger_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'billing.ledger_entries is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER forbid_mutation BEFORE UPDATE OR DELETE"
        " ON billing.ledger_entries FOR EACH ROW"
        " EXECUTE FUNCTION billing.forbid_ledger_mutation()"
    )
    op.execute("GRANT SELECT, INSERT ON billing.ledger_entries TO app_rt")
    op.execute("REVOKE UPDATE, DELETE ON billing.ledger_entries FROM app_rt")

    # -- billing.invoices: gain an ad-order parent ----------------------
    op.alter_column("invoices", "subscription_id", nullable=True, schema="billing")
    op.add_column(
        "invoices",
        sa.Column("order_id", _uuid, sa.ForeignKey("billing.ad_orders.id"), nullable=True),
        schema="billing",
    )
    op.add_column(
        "invoices",
        sa.Column("invoice_number", sa.Text(), nullable=True, unique=True),
        schema="billing",
    )
    op.add_column(
        "invoices", sa.Column("taxable_paise", sa.Integer(), nullable=True), schema="billing"
    )
    op.add_column("invoices", sa.Column("gst_paise", sa.Integer(), nullable=True), schema="billing")
    op.create_index("ix_billing_invoices_order_id", "invoices", ["order_id"], schema="billing")
    op.create_check_constraint(
        op.f("ck_billing_invoices_parent"),
        "invoices",
        "subscription_id IS NOT NULL OR order_id IS NOT NULL",
        schema="billing",
    )

    # billing.invoice_number_seq: the ops-facing sequential invoice number
    # (Task 10 fills invoice_number from it on generation; unused by this
    # migration otherwise).
    op.execute("CREATE SEQUENCE billing.invoice_number_seq")
    op.execute("GRANT USAGE ON SEQUENCE billing.invoice_number_seq TO app_rt")

    # -- ads.campaigns: the itemized quote snapshot ---------------------
    # money-path review 2a: the chain-of-custody fix. ads already stores the
    # scalar price_paise/price_subtotal_paise/price_gst_paise/rate_card_
    # version columns (0033); this ADDS the full itemized snapshot (line
    # items + rates + tier + multiplier) alongside them so billing can copy
    # a real invoice-grade quote into AdOrder.quote instead of a bare
    # 4-number reconstruction. Nullable: pre-existing campaigns (and any
    # future house/admin campaign) simply have quote=NULL - never re-derived
    # from it, the scalar columns remain authoritative for pricing.
    op.add_column("campaigns", sa.Column("quote", postgresql.JSONB(), nullable=True), schema="ads")


def downgrade() -> None:
    op.drop_column("campaigns", "quote", schema="ads")

    op.execute("DROP SEQUENCE billing.invoice_number_seq")

    op.drop_constraint(
        op.f("ck_billing_invoices_parent"), "invoices", schema="billing", type_="check"
    )
    op.drop_index("ix_billing_invoices_order_id", table_name="invoices", schema="billing")
    op.drop_column("invoices", "gst_paise", schema="billing")
    op.drop_column("invoices", "taxable_paise", schema="billing")
    op.drop_column("invoices", "invoice_number", schema="billing")
    op.drop_column("invoices", "order_id", schema="billing")
    # data loss: every ad-order invoice (subscription_id IS NULL) cannot
    # survive subscription_id going back to NOT NULL - deleted here.
    op.execute("DELETE FROM billing.invoices WHERE subscription_id IS NULL")
    op.alter_column("invoices", "subscription_id", nullable=False, schema="billing")

    op.execute("DROP TRIGGER IF EXISTS forbid_mutation ON billing.ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS billing.forbid_ledger_mutation()")
    op.drop_table("ledger_entries", schema="billing")

    op.drop_table("ad_orders", schema="billing")
