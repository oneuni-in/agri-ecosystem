# backend/core/alembic/versions/0025_vendor_dashboard.py
"""vendor dashboard v1 (D26): tier intent + delivery windows + profile views.

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-24

"""
# -- THREAT/NOTES:
# - premium_requested_at is INTENT ONLY (owner-writable via tier-selection);
#   subscription_tier stays server-set (admin route / billing at launch) -
#   fake-premium threat model.
# - profile_views is append-only BY GRANT (SELECT+INSERT, no UPDATE/DELETE):
#   a view count must never be editable through the app role.
# - viewer_hash is the ads-style daily-rotating pseudonym; unique
#   (business_id, viewer_hash) IS the 1-view/viewer/business/UTC-day dedupe
#   (the hash rotates daily, so the pair is day-scoped by construction).
# - pincode is nullable: the beacon may fire without browsing context.
# - downgrade drops the view history and both columns.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("premium_requested_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        schema="directory",
    )
    op.add_column(
        "businesses",
        sa.Column("delivery_windows", postgresql.JSONB, nullable=True),
        schema="directory",
    )

    op.create_table(
        "profile_views",
        pk_column(),
        sa.Column(
            "business_id",
            _uuid,
            sa.ForeignKey("directory.businesses.id"),
            nullable=False,
        ),
        sa.Column("pincode", sa.Text, nullable=True),
        sa.Column("viewer_hash", sa.Text, nullable=False),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        schema="directory",
    )
    op.create_index(
        "uq_directory_profile_views_dedupe",
        "profile_views",
        ["business_id", "viewer_hash"],
        unique=True,
        schema="directory",
    )
    op.create_index(
        "ix_directory_profile_views_business_occurred",
        "profile_views",
        ["business_id", "occurred_at"],
        schema="directory",
    )
    op.execute("GRANT SELECT, INSERT ON directory.profile_views TO app_rt")
    op.execute("REVOKE UPDATE, DELETE ON directory.profile_views FROM app_rt")


def downgrade() -> None:
    op.drop_table("profile_views", schema="directory")
    op.drop_column("businesses", "delivery_windows", schema="directory")
    op.drop_column("businesses", "premium_requested_at", schema="directory")
