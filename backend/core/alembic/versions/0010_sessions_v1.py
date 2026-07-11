"""sessions v1: web sessions table + refresh-family columns (D09).

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-11

"""
# -- THREAT/NOTES:
# downgrade data loss: drops sessions_web (every id.agri.in login) and the
#   refresh-family columns (rotation lineage). Pre-launch this is "everyone
#   logs in again" - acceptable and reversible by design.
# locks: sessions_refresh is empty until this spec's code ships, so the
#   NOT NULL ADD COLUMNs take a brief exclusive lock on an empty table;
#   CREATE TABLE/INDEX on new objects; negligible.
# rollout: run after 0009. No seed data. Revocation is revoked_at, never
#   DELETE - the device manager and reuse forensics read revoked rows.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions_web",
        pk_column(),
        *timestamp_columns(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.users.id"),
            nullable=False,
        ),
        sa.Column("sid_hash", sa.Text, unique=True, nullable=False),
        sa.Column("device_fingerprint", sa.Text, nullable=True),
        sa.Column("device_label", sa.Text, nullable=True),
        sa.Column("ip", sa.Text, nullable=True),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_index(
        "ix_identity_sessions_web_user_id", "sessions_web", ["user_id"], schema="identity"
    )
    op.create_index(
        "ix_identity_sessions_web_user_active",
        "sessions_web",
        ["user_id", "revoked_at"],
        schema="identity",
    )
    op.add_column(
        "sessions_refresh",
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        schema="identity",
    )
    op.add_column(
        "sessions_refresh",
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.oauth_clients.id"),
            nullable=False,
        ),
        schema="identity",
    )
    op.add_column(
        "sessions_refresh",
        sa.Column("device_fingerprint", sa.Text, nullable=True),
        schema="identity",
    )
    op.add_column(
        "sessions_refresh",
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_index(
        "ix_identity_sessions_refresh_family_id",
        "sessions_refresh",
        ["family_id"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_sessions_refresh_user_active",
        "sessions_refresh",
        ["user_id", "revoked_at"],
        schema="identity",
    )


def downgrade() -> None:
    op.drop_index("ix_identity_sessions_refresh_user_active", "sessions_refresh", schema="identity")
    op.drop_index("ix_identity_sessions_refresh_family_id", "sessions_refresh", schema="identity")
    op.drop_column("sessions_refresh", "last_used_at", schema="identity")
    op.drop_column("sessions_refresh", "device_fingerprint", schema="identity")
    op.drop_column("sessions_refresh", "client_id", schema="identity")
    op.drop_column("sessions_refresh", "family_id", schema="identity")
    op.drop_index("ix_identity_sessions_web_user_active", "sessions_web", schema="identity")
    op.drop_index("ix_identity_sessions_web_user_id", "sessions_web", schema="identity")
    op.drop_table("sessions_web", schema="identity")
