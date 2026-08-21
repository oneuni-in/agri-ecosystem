"""session device_kind (ID-U1 P8)

A coarse, human-readable device description stored per session so /devices can
answer "what device is this?".

Deliberately NOT a user_agent column. The list needs one recognisable
sentence ("Android - Chrome"), not a high-entropy fingerprint at rest; the
existing device_fingerprint hash keeps doing the security job. See
modules/identity/device_kind.py for the reasoning.

Nullable with no backfill: rows created before this migration genuinely do
not know, and the UI says "Unknown device" rather than inventing one. There
is nothing to derive them from - the raw UA was never stored.

Revision ID: 0054
Revises: 0053
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("sessions_web", "sessions_refresh")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("device_kind", sa.Text(), nullable=True),
            schema="identity",
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "device_kind", schema="identity")
