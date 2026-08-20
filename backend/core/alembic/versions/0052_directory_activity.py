"""A-U4b O11 (AG-A69): directory.activity - the "Live on agri.in" feed table.

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-20

One row per public happening: a need posted, a business joined, a review
approved, a lead sent. The home marquee reads the last N rows; nothing
else hangs off them.

THE PRIVACY CONTRACT IS THE SCHEMA. There is no user id column, no
person's name, no pincode, no phone, no email - so scrubbing is by
construction, not by filtering: a handler physically cannot store what
the table cannot hold. The only identifying fields are a business's name
and slug, which are already public on its directory page, and they are
nullable so a hook can honestly omit them when the business is not
publicly visible. Location is district/state - coarse on purpose; the
need's pincode is resolved to a district at write time and then DROPPED.

UNIQUE(kind, source_id) is the house idempotency idiom (coins
idempotency_key, profile_views dedupe precedent): proven by the DB, never
by app logic. Claim approval and verification approval both try to write
'business_joined' for the same business - the second insert is a no-op,
so one 'joined' row per business, ever.
"""

# -- THREAT/NOTES:
# - New table only, in the `directory` schema created by 0001. No existing
#   table is altered; no other module's data is touched.
# - downgrade drops directory.activity and its rows. Activity rows are
#   DERIVED decorations over domain writes that all live elsewhere (needs,
#   claims, reviews, inquiries) - loss is acceptable and the feed simply
#   restarts empty. Nothing references activity rows.
# - locks: CREATE TABLE/INDEX take catalog locks only; no table rewrite.
# - PII: none by construction - no user id, no person name, no pincode,
#   no contact column exists (see docstring; this is the design's point).
# - UNIQUE(kind, source_id) = DB-proven idempotency (coins precedent).
# - GRANT SELECT, INSERT, DELETE only - deliberately NO UPDATE: a feed row
#   is never edited, only written, read, and (eventually) pruned.
# - rollout: the read route is gated by `agri_live_feed`, seeded OFF in
#   0037 and NOT flipped by this migration or this PR. Hooks write rows
#   regardless of the flag (cheap, invisible), so the feed is warm on
#   flip day instead of empty.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity",
        pk_column(),
        *timestamp_columns(),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("district", sa.Text, nullable=True),
        sa.Column("state", sa.Text, nullable=True),
        sa.Column("business_name", sa.Text, nullable=True),
        sa.Column("business_slug", sa.Text, nullable=True),
        sa.Column("rating", sa.SmallInteger, nullable=True),
        sa.CheckConstraint(
            "kind IN ('need_posted', 'business_joined', 'review_approved', 'lead_sent')",
            name="activity_kind_known",
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="activity_rating_1_5"),
        sa.UniqueConstraint("kind", "source_id", name="uq_directory_activity_kind_source"),
        schema="directory",
    )
    op.create_index(
        "ix_directory_activity_occurred_at",
        "activity",
        [sa.text("occurred_at DESC")],
        schema="directory",
    )
    # Explicit per-table GRANT to app_rt (the 0023/0027/0038/0045 precedent),
    # never a blanket GRANT ON ALL TABLES. No UPDATE on purpose: rows are
    # written once and pruned, never edited.
    op.execute("GRANT SELECT, INSERT, DELETE ON directory.activity TO app_rt")


def downgrade() -> None:
    op.drop_table("activity", schema="directory")
