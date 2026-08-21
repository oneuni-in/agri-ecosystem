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

# -- THREAT/NOTES:
# - Adds one NULLABLE text column to two tables. No default, no backfill,
#   so postgres records a catalog change and rewrites no rows: the lock is
#   brief and safe against a running app.
# - PII posture is the POINT of this column's shape. It stores a coarse
#   derived string ("Android - Chrome"), never the raw user agent, so the
#   session row keeps strictly LESS identifying material than the obvious
#   alternative would have. device_fingerprint continues to do the
#   security binding; this is only what the /devices list shows a person
#   about their own sessions.
# - Blast radius if wrong: rows read NULL and the UI says "Unknown
#   device". No auth, revocation or rotation path depends on this value -
#   it is display-only.
# - Pre-existing rows stay NULL forever and there is nothing to derive
#   them from, because the raw UA was never stored. That is intentional,
#   not an incomplete backfill.
# - Downgrade drops the column; nothing else references it.

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
