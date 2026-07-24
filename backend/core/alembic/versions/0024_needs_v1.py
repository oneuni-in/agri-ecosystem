# backend/core/alembic/versions/0024_needs_v1.py
"""needs v1: user-side subscription-intent needs + inquiry fan-out link (D25).

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-24

"""
# -- THREAT/NOTES:
# - needs are authed-only (require_auth route; phone-verified by construction
#   via OTP login) - no guest rows, from_user_id is NOT NULL.
# - payload JSONB carries quantity/type/schedule/delivery preference, never
#   contact values. voice_key is a storage key (auth-gated serving), never a
#   URL and never a public-read prefix.
# - inquiries.need_id links fan-out children; nullable because D18
#   single-route inquiries predate needs. No cascade - needs are never
#   deleted.
# - per-table GRANT (0020/0023 precedent); needs are mutable state (status
#   transitions) so app_rt keeps UPDATE. NEVER a blanket schema grant.
# - downgrade drops the need history and the fan-out links.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM("open", "fulfilled", "closed", name="need_status", schema="leads").create(
        bind, checkfirst=True
    )
    status_col = postgresql.ENUM(name="need_status", schema="leads", create_type=False)

    op.create_table(
        "needs",
        pk_column(),
        sa.Column("from_user_id", _uuid, nullable=False),
        sa.Column("pincode", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", status_col, nullable=False, server_default="open"),
        sa.Column("accepted_business_id", _uuid, nullable=True),
        sa.Column("voice_key", sa.Text, nullable=True),
        *timestamp_columns(),
        schema="leads",
    )
    op.create_index(
        "ix_leads_needs_from_user_id_id", "needs", ["from_user_id", "id"], schema="leads"
    )

    op.add_column(
        "inquiries",
        sa.Column("need_id", _uuid, sa.ForeignKey("leads.needs.id"), nullable=True),
        schema="leads",
    )
    op.create_index("ix_leads_inquiries_need_id_id", "inquiries", ["need_id", "id"], schema="leads")

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON leads.needs TO app_rt")


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_leads_inquiries_need_id_id", table_name="inquiries", schema="leads")
    op.drop_column("inquiries", "need_id", schema="leads")
    op.drop_table("needs", schema="leads")
    sa.Enum(name="need_status", schema="leads").drop(bind, checkfirst=True)
