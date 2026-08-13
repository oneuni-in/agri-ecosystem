# backend/core/alembic/versions/0036_review_replies.py
"""review replies v1 (U2 Group C): a business's moderated response to a review.

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-12

"""
# -- THREAT/NOTES:
# - New table directory.review_replies. UGC by the vendor that the public
#   reads: moderation_status defaults 'pending', only 'approved' replies
#   surface publicly (D18 rule, unchanged). Soft-deleted, never hard-deleted.
# - One reply per review (uq on review_id): a business gives one official
#   response. review_id/business_id are plain UUIDs (no cross-FK, the
#   convention reviews itself follows); the service validates ownership +
#   that the review exists and is approved.
# - reuses the existing public.moderation_status enum (ugc_column) — no new
#   enum. create_table + indexes only, safe online, no table rewrites.
# - explicit GRANT to app_rt mirrors 0019 (0013's default privileges cover
#   new directory tables, but the grant keeps the intent legible and CRUD is
#   needed: UPDATE for moderation + soft-delete).
# - downgrade drops the table (reply content loss); no data outside it.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, soft_delete_column, timestamp_columns, ugc_column

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "review_replies",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        ugc_column(),
        sa.Column("review_id", _uuid, nullable=False),
        sa.Column("business_id", _uuid, nullable=False),
        sa.Column("author_user_id", _uuid, nullable=False),
        sa.Column("body", postgresql.JSONB, nullable=False),
        sa.UniqueConstraint("review_id", name="uq_directory_review_replies_one_per_review"),
        schema="directory",
    )
    op.create_index(
        "ix_directory_review_replies_review_id",
        "review_replies",
        ["review_id"],
        schema="directory",
    )
    op.create_index(
        "ix_directory_review_replies_business_id",
        "review_replies",
        ["business_id"],
        schema="directory",
    )
    op.create_index(
        "ix_directory_review_replies_moderation_status_id",
        "review_replies",
        ["moderation_status", "id"],
        schema="directory",
    )
    op.create_index(
        "ix_directory_review_replies_review_status",
        "review_replies",
        ["review_id", "moderation_status"],
        schema="directory",
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON directory.review_replies TO app_rt")


def downgrade() -> None:
    op.drop_index("ix_directory_review_replies_review_status", "review_replies", schema="directory")
    op.drop_index(
        "ix_directory_review_replies_moderation_status_id",
        "review_replies",
        schema="directory",
    )
    op.drop_index("ix_directory_review_replies_business_id", "review_replies", schema="directory")
    op.drop_index("ix_directory_review_replies_review_id", "review_replies", schema="directory")
    op.drop_table("review_replies", schema="directory")
