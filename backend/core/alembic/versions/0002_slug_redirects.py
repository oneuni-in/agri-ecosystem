"""Slug redirects table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-09

"""
# -- THREAT/NOTES:
# downgrade data loss: drops slug_redirects; recorded 301s (SEO continuity for
#   renamed public pages) are lost and old URLs start 404ing again.
# locks: single CREATE/DROP TABLE on an empty table; negligible.
# rollout: middleware reads this table only on 404 GET/HEAD, safe to apply live.

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "slug_redirects",
        pk_column(),
        *timestamp_columns(),
        sa.Column("old_path", sa.Text, nullable=False),
        sa.Column("new_path", sa.Text, nullable=False),
    )
    op.create_index("ix_slug_redirects_old_path", "slug_redirects", ["old_path"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_slug_redirects_old_path", table_name="slug_redirects")
    op.drop_table("slug_redirects")
