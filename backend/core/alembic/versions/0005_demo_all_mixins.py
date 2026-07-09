"""Demo table proving the full mixin column set migrates up and down.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-09

"""
# -- THREAT/NOTES:
# downgrade data loss: none that matters - _demo_all_mixins is a scaffolding
#   showcase (D03 definition-of-done), holds no product data, and is dropped
#   once the first real module table (D06 identity) exists.
# locks: CREATE/DROP TABLE on an empty table; negligible.
# rollout: no readers or writers; exists so CI exercises every mixin column
#   helper through a real upgrade/downgrade cycle.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import (
    pk_column,
    soft_delete_column,
    timestamp_columns,
    ugc_column,
)

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "_demo_all_mixins",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        ugc_column(),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("title", postgresql.JSONB, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("_demo_all_mixins")
