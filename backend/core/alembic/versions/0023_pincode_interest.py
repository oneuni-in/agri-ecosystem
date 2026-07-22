# backend/core/alembic/versions/0023_pincode_interest.py
"""pincode interest: warm empty-state demand capture (D23).

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-22

"""
# -- THREAT/NOTES:
# - Guest-writable demand log (public POST /leads/pincode-interest,
#   optional_auth). Rows carry only what the submitter volunteers
#   (pincode + optional contact/milk_type) plus a nullable from_user_id
#   when authed - no coverage routing, no vendor inbox, no PII beyond the
#   optional contact string.
# - downgrade drops the whole demand history (seeding-priority signal loss).
# - leads schema + app_rt default privileges exist since 0001/0013; the
#   explicit per-table GRANT below keeps the profile reviewable (0020
#   precedent). NEVER a blanket GRANT ON ALL TABLES IN SCHEMA.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "pincode_interest",
        pk_column(),
        sa.Column("pincode", sa.Text, nullable=False),
        sa.Column("district", sa.Text, nullable=True),
        sa.Column("contact", sa.Text, nullable=True),
        sa.Column("from_user_id", _uuid, nullable=True),
        sa.Column("milk_type", sa.Text, nullable=True),
        *timestamp_columns(),
        schema="leads",
    )
    op.create_index(
        "ix_leads_pincode_interest_pincode_id",
        "pincode_interest",
        ["pincode", "id"],
        schema="leads",
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON leads.pincode_interest TO app_rt")


def downgrade() -> None:
    op.drop_table("pincode_interest", schema="leads")
