"""M4: automatic pincode tiers - geo.pincode_tiers + append-only history.

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-04

Population provenance & approximation (spec M4.A: document honestly):
- Pincode universe: GeoNames IN.zip (CC BY 4.0), the D03 source.
- TN populations: Census of India 2011 Primary Census Abstract town/village
  level (data.gov.in / Census NADA, NDSAP open licence), matched to pincodes
  by normalized place-name join within district; census units matching N
  pincodes split their population evenly (no double count); unmatched
  village population apportioned across the district's pincodes.
- Pan-India: district-level PCA apportioned per pincode (dormant, Stage-B).
- Census 2011 undercounts 2026 populations; tiers depend only on the
  DISTRIBUTION (percentiles), so a roughly uniform undercount does not move
  tier boundaries. Per-row quality recorded in population_grade. Full
  provenance: backend/core/data/geo/SOURCES.md.
"""
# -- THREAT/NOTES:
# downgrade data loss: drops geo.pincode_tiers + geo.pincode_tier_history
#   (recomputable: scripts/load_pincode_tiers.py over the committed CSV)
#   and ads.delivery_decisions.tier (sampled analytics column).
# locks: CREATE TABLE + nullable ADD COLUMN - brief, no rewrites.
# rollout: run scripts/load_pincode_tiers.py after upgrade; until then
#   get_tier() returns the default T4 and delivery is unaffected.

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pincode_tiers",
        pk_column(),
        *timestamp_columns(),
        sa.Column("pincode", sa.Text, nullable=False, unique=True),
        sa.Column("population", sa.BigInteger, nullable=False),
        sa.Column("population_grade", sa.Text, nullable=False),
        sa.Column("tier", sa.SmallInteger, nullable=False, server_default="4"),
        sa.Column("user_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("tier_changed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("method", sa.Text, nullable=False, server_default="population"),
        schema="geo",
    )
    # op.f(): final names - without it the metadata naming convention
    # re-wraps them and downgrade's drop cannot find them (M3 trap).
    op.create_check_constraint(
        op.f("ck_geo_pincode_tiers_tier_range"),
        "pincode_tiers",
        "tier BETWEEN 1 AND 5",
        schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tiers_population"),
        "pincode_tiers",
        "population >= 0",
        schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tiers_user_count"),
        "pincode_tiers",
        "user_count >= 0",
        schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tiers_method"),
        "pincode_tiers",
        "method IN ('population', 'population+users')",
        schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tiers_grade"),
        "pincode_tiers",
        "population_grade IN ('town', 'village', 'district_apportioned')",
        schema="geo",
    )

    op.create_table(
        "pincode_tier_history",
        pk_column(),
        # append-only: created_at only (0013 rule)
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("pincode", sa.Text, nullable=False, index=True),
        sa.Column("old_tier", sa.SmallInteger, nullable=True),
        sa.Column("new_tier", sa.SmallInteger, nullable=False),
        sa.Column("old_method", sa.Text, nullable=True),
        sa.Column("new_method", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tier_history_reason"),
        "pincode_tier_history",
        "reason IN ('initial', 'population_recompute', 'user_promotion', 'admin_override')",
        schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tier_history_new_tier"),
        "pincode_tier_history",
        "new_tier BETWEEN 1 AND 5",
        schema="geo",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION geo.forbid_tier_history_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'geo.pincode_tier_history is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER forbid_mutation BEFORE UPDATE OR DELETE"
        " ON geo.pincode_tier_history FOR EACH ROW"
        " EXECUTE FUNCTION geo.forbid_tier_history_mutation()"
    )
    # geo default privileges already grant app_rt DML (0013); explicit for
    # reviewability + revoke mutation on the append-only table (0031 idiom).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON geo.pincode_tiers TO app_rt")
    op.execute("GRANT SELECT, INSERT ON geo.pincode_tier_history TO app_rt")
    op.execute("REVOKE UPDATE, DELETE ON geo.pincode_tier_history FROM app_rt")

    # M4.D: tier available to delivery analytics (filled via get_tier()).
    op.add_column(
        "delivery_decisions",
        sa.Column("tier", sa.SmallInteger(), nullable=True),
        schema="ads",
    )


def downgrade() -> None:
    op.drop_column("delivery_decisions", "tier", schema="ads")
    op.execute("DROP TRIGGER IF EXISTS forbid_mutation ON geo.pincode_tier_history")
    op.execute("DROP FUNCTION IF EXISTS geo.forbid_tier_history_mutation()")
    op.drop_table("pincode_tier_history", schema="geo")
    op.drop_table("pincode_tiers", schema="geo")
