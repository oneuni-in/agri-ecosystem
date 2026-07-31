# backend/core/alembic/versions/0031_ads_delivery_v1.py
"""ads delivery v1 (M3): campaign serve budgets + why-served decision log.

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-31

"""
# -- THREAT/NOTES:
# - budget_serves_total is a SERVE-CREDIT ceiling (NULL = unlimited - house
#   ads never hit the row). Actual money stays out of the ads schema (M5
#   owns billing); the atomic conditional UPDATE in
#   modules/ads/service.consume_budget is what closes the budget-race threat
#   (concurrent serves must never spend a credit twice).
# - delivery_decisions is append-only BY GRANT (SELECT+INSERT only) AND by
#   trigger (reuses 0022's ads.forbid_tracking_mutation, so not even the
#   owner role can rewrite the dispute-resolution record).
# - viewer_hash is the daily-rotating pseudonym; pincode/category are serve
#   context. NO user identifier lands here (threat: delivery-log PII).
# - The log is SAMPLED at serve time (settings.ads_delivery_log_sample), so
#   volume stays small enough for a plain table (profile_views precedent) -
#   no daily partitioning.
# - downgrade drops the log and both budget columns (budget state is lost;
#   acceptable pre-launch).

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("budget_serves_total", sa.Integer(), nullable=True),
        schema="ads",
    )
    op.add_column(
        "campaigns",
        sa.Column("budget_serves_used", sa.Integer(), nullable=False, server_default="0"),
        schema="ads",
    )
    # op.f(): the name is final - without it the metadata naming convention
    # re-wraps it (ck_campaigns_ck_...) and downgrade's drop cannot find it
    # (caught by CI migrate_check's downgrade-base pass).
    op.create_check_constraint(
        op.f("ck_ads_campaigns_budget_total"),
        "campaigns",
        "budget_serves_total IS NULL OR budget_serves_total >= 0",
        schema="ads",
    )
    op.create_check_constraint(
        op.f("ck_ads_campaigns_budget_used"),
        "campaigns",
        "budget_serves_used >= 0",
        schema="ads",
    )

    op.create_table(
        "delivery_decisions",
        pk_column(),
        sa.Column("campaign_id", _uuid, nullable=False),
        sa.Column("placement_id", _uuid, nullable=False),
        sa.Column("creative_id", _uuid, nullable=False),
        sa.Column("slot_key", sa.Text(), nullable=False),
        sa.Column("pincode", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("why_served", sa.Text(), nullable=False),
        sa.Column("viewer_hash", sa.Text(), nullable=False),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        schema="ads",
    )
    op.create_index(
        "ix_ads_delivery_decisions_campaign_day",
        "delivery_decisions",
        ["campaign_id", "occurred_at"],
        schema="ads",
    )
    op.execute(
        "CREATE TRIGGER delivery_decisions_append_only "
        "BEFORE UPDATE OR DELETE ON ads.delivery_decisions "
        "FOR EACH ROW EXECUTE FUNCTION ads.forbid_tracking_mutation()"
    )
    op.execute("GRANT SELECT, INSERT ON ads.delivery_decisions TO app_rt")
    op.execute("REVOKE UPDATE, DELETE ON ads.delivery_decisions FROM app_rt")


def downgrade() -> None:
    op.drop_table("delivery_decisions", schema="ads")
    op.drop_constraint(
        op.f("ck_ads_campaigns_budget_used"), "campaigns", schema="ads", type_="check"
    )
    op.drop_constraint(
        op.f("ck_ads_campaigns_budget_total"), "campaigns", schema="ads", type_="check"
    )
    op.drop_column("campaigns", "budget_serves_used", schema="ads")
    op.drop_column("campaigns", "budget_serves_total", schema="ads")
