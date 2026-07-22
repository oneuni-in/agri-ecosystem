# backend/core/alembic/versions/0022_ads_v1.py
"""D21 ads: campaigns, creatives, placements, partitioned impressions/clicks.

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-21

"""
# -- THREAT/NOTES:
# - impressions/clicks are append-only raw logs (click-fraud forensics, DPDP
#   minimal: viewer_hash rotates daily, no stable identifier). Immutability is
#   trigger-level (0012 ledger precedent) AND grant-level; the 0013 schema-wide
#   default privileges would re-grant DML on new partitions, but the trigger
#   clones onto every partition, so direct-partition writes stay blocked.
# - PARTITION BY RANGE(occurred_at), daily. This migration pre-creates
#   today..today+7 plus a DEFAULT partition per table so inserts NEVER fail on
#   a new day even if the maintenance worker is down (spec: "cron/maintenance
#   job OR default partition" - we ship both). modules/ads/maintenance.py
#   extends the daily set going forward; partition DDL here is deliberately
#   inlined (migrations are frozen snapshots, no app imports beyond helpers).
# - Per-table grants only (0019/0021 precedent).
# - Downgrade drops schema-local objects only; ads has no rows pre-launch
#   (ads_enabled=false), so data loss is acceptable and instant.
# - No long locks: all CREATEs, nothing rewrites existing tables.

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns, ugc_column

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRACKING_TABLES = ("impressions", "clicks")


def _create_daily_partitions(table: str, start_days: int, end_days: int) -> None:
    today = datetime.now(UTC).date()
    for offset in range(start_days, end_days + 1):
        day = today + timedelta(days=offset)
        nxt = day + timedelta(days=1)
        op.execute(
            f'CREATE TABLE IF NOT EXISTS ads."{table}_p{day:%Y%m%d}" '
            f"PARTITION OF ads.{table} "
            f"FOR VALUES FROM ('{day.isoformat()}') TO ('{nxt.isoformat()}')"
        )


def upgrade() -> None:
    op.create_table(
        "campaigns",
        pk_column(),
        sa.Column("advertiser_business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("budget_display", sa.Text(), server_default="", nullable=False),
        sa.Column("flight_start", sa.Date(), nullable=False),
        sa.Column("flight_end", sa.Date(), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('draft','active','paused','archived')",
            name="ck_ads_campaigns_status",
        ),
        sa.CheckConstraint("flight_end >= flight_start", name="ck_ads_campaigns_flight"),
        schema="ads",
    )
    op.create_index(
        "ix_ads_campaigns_advertiser_business_id",
        "campaigns",
        ["advertiser_business_id"],
        schema="ads",
    )

    op.create_table(
        "creatives",
        pk_column(),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ads.campaigns.id"),
            nullable=False,
        ),
        sa.Column(
            "media_keys",
            postgresql.JSONB(),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("copy", postgresql.JSONB(), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        ugc_column(),
        *timestamp_columns(),
        schema="ads",
    )
    op.create_index("ix_ads_creatives_campaign_id", "creatives", ["campaign_id"], schema="ads")

    op.create_table(
        "placements",
        pk_column(),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ads.campaigns.id"),
            nullable=False,
        ),
        sa.Column("slot_key", sa.Text(), nullable=False),
        sa.Column(
            "geo_target",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("weight", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("status IN ('active','paused')", name="ck_ads_placements_status"),
        sa.CheckConstraint("weight >= 1", name="ck_ads_placements_weight"),
        schema="ads",
    )
    op.create_index("ix_ads_placements_campaign_id", "placements", ["campaign_id"], schema="ads")
    op.create_index("ix_ads_placements_slot_key", "placements", ["slot_key"], schema="ads")

    # -- partitioned tracking tables: raw SQL (alembic has no first-class
    # partitioning support). PK must contain the partition key.
    for table in TRACKING_TABLES:
        op.execute(
            f"""
            CREATE TABLE ads.{table} (
                id UUID NOT NULL,
                placement_id UUID NOT NULL,
                creative_id UUID NOT NULL,
                slot_key TEXT NOT NULL,
                viewer_hash TEXT NOT NULL,
                pincode TEXT,
                occurred_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (id, occurred_at)
            ) PARTITION BY RANGE (occurred_at)
            """
        )
        op.execute(
            f"CREATE INDEX ix_ads_{table}_placement_day ON ads.{table} (placement_id, occurred_at)"
        )
        op.execute(f'CREATE TABLE ads."{table}_default" PARTITION OF ads.{table} DEFAULT')
        _create_daily_partitions(table, 0, 7)

    # -- trigger-level immutability (clones to every partition, incl. future
    # ones created by maintenance.py and the DEFAULT partition)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ads.forbid_tracking_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ads.% is append-only', TG_TABLE_NAME;
        END $$ LANGUAGE plpgsql
        """
    )
    for table in TRACKING_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE "
            f"ON ads.{table} FOR EACH ROW EXECUTE FUNCTION ads.forbid_tracking_mutation()"
        )

    # -- explicit per-table grants (0019/0021 precedent - never schema-wide)
    for table in ("campaigns", "creatives", "placements"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ads.{table} TO app_rt")
    for table in TRACKING_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON ads.{table} TO app_rt")
        op.execute(f"REVOKE UPDATE, DELETE ON ads.{table} FROM app_rt")


def downgrade() -> None:
    for table in TRACKING_TABLES:
        op.execute(f"DROP TABLE IF EXISTS ads.{table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS ads.forbid_tracking_mutation()")
    op.drop_table("placements", schema="ads")
    op.drop_table("creatives", schema="ads")
    op.drop_table("campaigns", schema="ads")
