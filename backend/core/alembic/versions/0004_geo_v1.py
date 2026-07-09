"""geo schema v1: states, districts, pincode centroids.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-09

"""
# -- THREAT/NOTES:
# downgrade data loss: drops the three geo reference tables. Content is fully
#   re-creatable from the committed snapshot via scripts/load_geo.py.
# locks: CREATE/DROP TABLE on empty tables; negligible.
# rollout: tables ship empty; run scripts/load_geo.py after upgrading.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "states",
        pk_column(),
        *timestamp_columns(),
        sa.Column("lgd_code", sa.Integer, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("name_ta", sa.Text, nullable=True),
        schema="geo",
    )
    op.create_table(
        "districts",
        pk_column(),
        *timestamp_columns(),
        sa.Column("lgd_code", sa.Integer, nullable=False, unique=True),
        sa.Column(
            "state_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geo.states.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("name_ta", sa.Text, nullable=True),
        schema="geo",
    )
    op.create_table(
        "pincodes",
        pk_column(),
        *timestamp_columns(),
        sa.Column("pincode", sa.Text, nullable=False, unique=True),
        sa.Column(
            "district_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geo.districts.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("centroid_lat", sa.Numeric(9, 6), nullable=False),
        sa.Column("centroid_lon", sa.Numeric(9, 6), nullable=False),
        schema="geo",
    )


def downgrade() -> None:
    op.drop_table("pincodes", schema="geo")
    op.drop_table("districts", schema="geo")
    op.drop_table("states", schema="geo")
