# backend/core/alembic/versions/0030_trust_safety_v1.py
"""M1.5 trust & safety: user reports + business enforcement soft-state.

Adds directory.reports (user reports of businesses, moderated through the
unified ops queue; never public), a 'disabled' value to the
directory.business_status enum, and two enforcement columns on
directory.businesses (enforcement_reason shown to the owner while enforced,
enforcement_prior_status restored by the reinstate action).

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-30

"""
# -- THREAT/NOTES:
# downgrade data loss: drops directory.reports (all user reports) and the
#   two enforcement columns (reason + prior state for currently-enforced
#   businesses). The 'disabled' enum value CANNOT be removed from
#   directory.business_status (postgres has no ALTER TYPE DROP VALUE);
#   downgrade first flips any status='disabled' row to 'suspended' so no row
#   references the orphaned value, then leaves the value in place - harmless
#   and documented here. Accepted: forward-only in practice.
# locks: ALTER TYPE ADD VALUE takes a brief exclusive lock on the type;
#   ADD COLUMN (all nullable, no default rewrite) and CREATE TABLE are
#   metadata-only. No table rewrite, no index rebuild on existing tables.
# rollout: ALTER TYPE ... ADD VALUE runs inside alembic's transaction; the
#   new value is not used by any statement in this migration (PG12+ rule),
#   only by application writes after commit. Enforcement columns are NULL
#   for every existing row, matching status='active' semantics. reports is
#   a fresh table: pending-default UGC moderation, partial unique index
#   enforcing one OPEN report per (business, reporter) so re-reporting is
#   possible after a decision - the anti-brigading brake is the per-user
#   daily cap in settings (report_daily_cap), not this index.
# privacy: reporter_user_id is a plain UUID (no FK into identity, module
#   independence). Reports are admin-surface-only; nothing here is ever
#   rendered publicly or exposed to the reported vendor.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns, ugc_column

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

report_reason = postgresql.ENUM(
    "fake_listing",
    "wrong_info",
    "abusive",
    "fraud_scam",
    "other",
    name="report_reason",
    schema="directory",
)

business_status_ref = postgresql.ENUM(name="business_status", schema="directory", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    op.execute("ALTER TYPE directory.business_status ADD VALUE IF NOT EXISTS 'disabled'")

    op.add_column(
        "businesses",
        sa.Column("enforcement_reason", sa.Text, nullable=True),
        schema="directory",
    )
    op.add_column(
        "businesses",
        sa.Column("enforcement_prior_status", business_status_ref, nullable=True),
        schema="directory",
    )

    report_reason.create(bind, checkfirst=True)
    report_reason_ref = postgresql.ENUM(name="report_reason", schema="directory", create_type=False)
    op.create_table(
        "reports",
        pk_column(),
        *timestamp_columns(),
        ugc_column(),
        sa.Column(
            "business_id",
            _uuid,
            sa.ForeignKey("directory.businesses.id"),
            nullable=False,
        ),
        sa.Column("reporter_user_id", _uuid, nullable=False),
        sa.Column("reason", report_reason_ref, nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        schema="directory",
    )
    op.create_index(
        "ix_directory_reports_reporter_user_id",
        "reports",
        ["reporter_user_id"],
        schema="directory",
    )
    op.create_index(
        "uq_directory_reports_one_pending",
        "reports",
        ["business_id", "reporter_user_id"],
        unique=True,
        schema="directory",
        postgresql_where=sa.text("moderation_status = 'pending'"),
    )
    op.create_index(
        "ix_directory_reports_status_id",
        "reports",
        ["moderation_status", "id"],
        schema="directory",
    )
    # belt-and-braces (default privileges cover it): intent visible here
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON directory.reports TO app_rt")


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("reports", schema="directory")
    sa.Enum(name="report_reason", schema="directory").drop(bind, checkfirst=True)
    # no row may reference 'disabled' after downgrade (the value itself is
    # unremovable - see THREAT/NOTES)
    op.execute("UPDATE directory.businesses SET status = 'suspended' WHERE status = 'disabled'")
    op.drop_column("businesses", "enforcement_prior_status", schema="directory")
    op.drop_column("businesses", "enforcement_reason", schema="directory")
