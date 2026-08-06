# backend/core/alembic/versions/0033_ads_selfserve.py
"""M5: campaign lifecycle statuses + pricing columns + versioned rate card.

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-04

"""
# -- THREAT/NOTES:
# downgrade data loss: pricing columns and rate_card_versions dropped; lifecycle
#   statuses collapsed (pending_* -> draft, exhausted/expired -> archived) before
#   the CHECK is re-narrowed.
# locks: ALTER TABLE on ads.campaigns takes ACCESS EXCLUSIVE briefly; table is small.
# rollout: seeds rate card v1 so pricing works before any Ops edit. price_paise is
#   NULL for all pre-M5 (house/admin) campaigns - NULL means "not a paid campaign".
# per-table grants only (0019/0021/0022 precedent - ads schema has no blanket
#   default privileges), so rate_card_versions needs explicit GRANT before REVOKE.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

# 0022 created this CHECK inline (sa.CheckConstraint(name="ck_ads_campaigns_status")
# inside op.create_table without op.f()), so Base's naming convention re-wrapped it -
# verified against the live dev DB (pg_constraint), not guessed.
OLD_STATUS_CONSTRAINT = "ck_campaigns_ck_ads_campaigns_status"

LIFECYCLE = (
    "'draft','pending_payment','pending_moderation','active',"
    "'paused','exhausted','expired','archived'"
)
OLD_LIFECYCLE = "'draft','active','paused','archived'"

rate_card_versions_table = sa.table(
    "rate_card_versions",
    sa.column("id", _uuid),
    sa.column("version", sa.Integer),
    sa.column("config", postgresql.JSONB),
    schema="ads",
)

DEFAULT_RATE_CARD = {
    "cpm_paise": {"1": 30000, "2": 20000, "3": 12000, "4": 8000, "5": 5000},
    "flat_weekly_paise": {"1": 150000, "2": 100000, "3": 60000, "4": 40000, "5": 25000},
    "category_multipliers_bp": {"ghee": 12000, "paneer": 11000},
    "min_total_paise": 10000,
}


def upgrade() -> None:
    op.drop_constraint(op.f(OLD_STATUS_CONSTRAINT), "campaigns", schema="ads", type_="check")
    op.create_check_constraint(
        op.f("ck_ads_campaigns_status"), "campaigns", f"status IN ({LIFECYCLE})", schema="ads"
    )
    op.add_column("campaigns", sa.Column("pricing_model", sa.Text(), nullable=True), schema="ads")
    op.add_column("campaigns", sa.Column("price_paise", sa.Integer(), nullable=True), schema="ads")
    op.add_column(
        "campaigns", sa.Column("price_subtotal_paise", sa.Integer(), nullable=True), schema="ads"
    )
    op.add_column(
        "campaigns", sa.Column("price_gst_paise", sa.Integer(), nullable=True), schema="ads"
    )
    op.add_column(
        "campaigns", sa.Column("rate_card_version", sa.Integer(), nullable=True), schema="ads"
    )
    op.add_column(
        "campaigns",
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="ads",
    )
    op.add_column(
        "campaigns", sa.Column("daily_serve_cap", sa.Integer(), nullable=True), schema="ads"
    )
    op.create_check_constraint(
        op.f("ck_ads_campaigns_price_nonneg"),
        "campaigns",
        "price_paise IS NULL OR price_paise >= 0",
        schema="ads",
    )
    op.create_check_constraint(
        op.f("ck_ads_campaigns_price_parts_nonneg"),
        "campaigns",
        "(price_subtotal_paise IS NULL OR price_subtotal_paise >= 0)"
        " AND (price_gst_paise IS NULL OR price_gst_paise >= 0)",
        schema="ads",
    )
    op.create_check_constraint(
        op.f("ck_ads_campaigns_pricing_model"),
        "campaigns",
        "pricing_model IS NULL OR pricing_model IN ('cpm','flat_weekly')",
        schema="ads",
    )

    op.create_table(
        "rate_card_versions",
        pk_column(),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("created_by_user_id", _uuid, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="ads",
    )
    op.execute("GRANT SELECT, INSERT ON ads.rate_card_versions TO app_rt")
    op.execute("REVOKE UPDATE, DELETE ON ads.rate_card_versions FROM app_rt")

    op.bulk_insert(
        rate_card_versions_table,
        [{"id": uuid6.uuid7(), "version": 1, "config": DEFAULT_RATE_CARD}],
    )


def downgrade() -> None:
    op.drop_table("rate_card_versions", schema="ads")
    op.drop_constraint(
        op.f("ck_ads_campaigns_pricing_model"), "campaigns", schema="ads", type_="check"
    )
    op.drop_constraint(
        op.f("ck_ads_campaigns_price_parts_nonneg"), "campaigns", schema="ads", type_="check"
    )
    op.drop_constraint(
        op.f("ck_ads_campaigns_price_nonneg"), "campaigns", schema="ads", type_="check"
    )
    for col in (
        "daily_serve_cap",
        "paid_at",
        "rate_card_version",
        "price_gst_paise",
        "price_subtotal_paise",
        "price_paise",
        "pricing_model",
    ):
        op.drop_column("campaigns", col, schema="ads")
    op.execute(
        "UPDATE ads.campaigns SET status='draft'"
        " WHERE status IN ('pending_payment','pending_moderation')"
    )
    op.execute("UPDATE ads.campaigns SET status='archived' WHERE status IN ('exhausted','expired')")
    op.drop_constraint(op.f("ck_ads_campaigns_status"), "campaigns", schema="ads", type_="check")
    op.create_check_constraint(
        op.f(OLD_STATUS_CONSTRAINT), "campaigns", f"status IN ({OLD_LIFECYCLE})", schema="ads"
    )
