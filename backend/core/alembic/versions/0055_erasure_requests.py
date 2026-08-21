"""erasure requests (ID-U1 W4, DPDP 2023)

The soft-delete flow's audit trail: who asked to be erased, when the grace
window ends, what held it, and when it actually ran.

The row deliberately OUTLIVES the erased data. After execution it keeps the
request's shape - dates, status, hold reasons - and nothing identifying
beyond the FK, so "was this account erased, and when?" stays answerable to a
regulator after the personal data is gone.

Revision ID: 0055
Revises: 0054
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# -- THREAT/NOTES:
# - New table only. No existing table is touched, so no lock on live data
#   and no query plan changes.
# - Holds NO personal data: a user FK, a status, timestamps, and staff-
#   facing hold reasons that name another module's business state
#   ("directory:owns_business"), never a person. It is deliberately
#   readable after the subject's data is erased, so "was this account
#   erased, and when?" stays answerable to a regulator.
# - Blast radius if wrong: the DPDP erasure flow cannot record requests
#   and the admin queue is empty. Nothing is deleted by this migration,
#   and no erasure can run without a row here - the failure mode is
#   "deletion does not happen", never "deletion happens unrecorded".
# - The FK to identity.users is intentionally NOT ON DELETE CASCADE:
#   erasure scrubs the user row rather than deleting it (an immutable
#   coins ledger cannot lose an entry because its subject left), so the
#   parent always survives.
# - Downgrade drops the table, which discards the erasure audit trail -
#   acceptable only before any request exists.


def upgrade() -> None:
    op.create_table(
        "erasure_requests",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.users.id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("execute_after", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("hold_reasons", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="identity",
    )
    op.create_index(
        "ix_identity_erasure_requests_status_created",
        "erasure_requests",
        ["status", "created_at"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_erasure_requests_user",
        "erasure_requests",
        ["user_id"],
        schema="identity",
    )


def downgrade() -> None:
    op.drop_table("erasure_requests", schema="identity")
