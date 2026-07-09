"""Feature flags table + launch kill-switch seeds.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-09

"""
# -- THREAT/NOTES:
# downgrade data loss: drops feature_flags; any flags flipped since seed are
#   forgotten. billing/ads code paths must treat missing flags as disabled.
# locks: CREATE/DROP TABLE + two-row seed; negligible.
# rollout: readers cache for 30s (shared/flags.py); seeds ship disabled so
#   applying this revision changes no behaviour.

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from shared.migrations import timestamp_columns

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = op.create_table(
        "feature_flags",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("enabled", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("description", sa.Text, server_default="", nullable=False),
        *timestamp_columns(),
    )
    op.bulk_insert(
        table,
        [
            {"key": "billing_enabled", "enabled": False, "description": "master billing switch"},
            {"key": "ads_enabled", "enabled": False, "description": "master ads switch"},
        ],
    )


def downgrade() -> None:
    op.drop_table("feature_flags")
