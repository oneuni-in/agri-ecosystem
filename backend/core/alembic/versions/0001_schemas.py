"""Create module schemas and shared enums.

Revision ID: 0001
Revises:
Create Date: 2026-07-09

"""
# -- THREAT/NOTES:
# downgrade data loss: drops every module schema WITH CASCADE - all tables and
#   rows in them are destroyed. Acceptable only because this is the base revision.
# locks: CREATE/DROP SCHEMA take brief catalog locks; no table data involved.
# rollout: must be the first revision applied to a fresh database; nothing to backfill.

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = (
    "identity",
    "coins",
    "directory",
    "leads",
    "content",
    "market",
    "ads",
    "notify",
    "billing",
    "geo",
)


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    sa.Enum("pending", "approved", "rejected", name="moderation_status", schema="public").create(
        op.get_bind(), checkfirst=True
    )


def downgrade() -> None:
    sa.Enum(name="moderation_status", schema="public").drop(op.get_bind(), checkfirst=True)
    for schema in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
