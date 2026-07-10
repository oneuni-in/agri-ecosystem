"""identity schema v1: users, handle history, OTP, refresh sessions, emails,
RBAC (roles/permissions), profiles, addresses, preferences, AG-id sequence.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-10

"""
# -- THREAT/NOTES:
# downgrade data loss: drops every identity table, both identity enums, and the
#   agri_id sequence - all accounts, sessions and RBAC assignments are destroyed.
#   Acceptable now: pre-launch, no production users exist; after launch a
#   downgrade of this revision is an incident decision, never routine.
# locks: CREATE/DROP TABLE on empty tables, CREATE TYPE/SEQUENCE; negligible.
# rollout: tables ship empty; 0008 seeds the RBAC baseline. No readers or
#   writers until D07+ adds HTTP. otp_requests.code_hash is hash-only by
#   design - there is deliberately no plaintext code column to migrate later.

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, soft_delete_column, timestamp_columns

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _user_status() -> postgresql.ENUM:
    return postgresql.ENUM(
        "active",
        "suspended",
        "deleted",
        name="user_status",
        schema="identity",
        create_type=False,
    )


def _user_language() -> postgresql.ENUM:
    return postgresql.ENUM(
        "en",
        "ta",
        "hi",
        name="user_language",
        schema="identity",
        create_type=False,
    )


def _user_fk(*, index: bool = False, unique: bool = False) -> sa.Column[uuid.UUID]:
    return sa.Column(
        "user_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("identity.users.id"),
        nullable=False,
        index=index,
        unique=unique,
    )


def upgrade() -> None:
    bind = op.get_bind()
    sa.Enum("active", "suspended", "deleted", name="user_status", schema="identity").create(
        bind, checkfirst=True
    )
    sa.Enum("en", "ta", "hi", name="user_language", schema="identity").create(bind, checkfirst=True)
    op.execute("CREATE SEQUENCE identity.agri_id_seq")

    op.create_table(
        "users",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("phone", sa.Text, nullable=False, unique=True),
        sa.Column("phone_verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", _user_status(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("agri_id", sa.Text, nullable=False, unique=True),
        sa.Column("agri_id_changed_once", sa.Boolean, server_default=sa.false(), nullable=False),
        schema="identity",
    )
    op.create_table(
        "handles_history",
        pk_column(),
        *timestamp_columns(),
        _user_fk(index=True),
        sa.Column("old_agri_id", sa.Text, nullable=False),
        sa.Column("new_agri_id", sa.Text, nullable=False),
        schema="identity",
    )
    op.create_table(
        "otp_requests",
        pk_column(),
        *timestamp_columns(),
        sa.Column("phone", sa.Text, nullable=False, index=True),
        sa.Column("code_hash", sa.Text, nullable=False),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("ip", sa.Text, nullable=True),
        sa.Column("device_fingerprint", sa.Text, nullable=True),
        schema="identity",
    )
    op.create_table(
        "sessions_refresh",
        pk_column(),
        *timestamp_columns(),
        _user_fk(index=True),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("device_label", sa.Text, nullable=True),
        sa.Column("ip", sa.Text, nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "rotated_from",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.sessions_refresh.id"),
            nullable=True,
        ),
        schema="identity",
    )
    op.create_table(
        "emails",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        _user_fk(index=True),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_table(
        "roles",
        pk_column(),
        *timestamp_columns(),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        schema="identity",
    )
    op.create_table(
        "permissions",
        pk_column(),
        *timestamp_columns(),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        schema="identity",
    )
    op.create_table(
        "role_permissions",
        pk_column(),
        *timestamp_columns(),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.roles.id"),
            nullable=False,
        ),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.permissions.id"),
            nullable=False,
        ),
        sa.UniqueConstraint("role_id", "permission_id"),
        schema="identity",
    )
    op.create_table(
        "user_roles",
        pk_column(),
        *timestamp_columns(),
        _user_fk(),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.roles.id"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "role_id"),
        schema="identity",
    )
    op.create_table(
        "profiles",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        _user_fk(unique=True),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("avatar_key", sa.Text, nullable=True),
        sa.Column("state", sa.Text, nullable=True),
        sa.Column("district", sa.Text, nullable=True),
        sa.Column("pincode", sa.Text, nullable=True),
        sa.Column("language", _user_language(), server_default=sa.text("'en'"), nullable=False),
        sa.Column(
            "interests", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("completion_score", sa.Integer, server_default=sa.text("0"), nullable=False),
        schema="identity",
    )
    op.create_table(
        "addresses",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        _user_fk(index=True),
        sa.Column("label", sa.Text, nullable=True),
        sa.Column("line1", sa.Text, nullable=False),
        sa.Column("line2", sa.Text, nullable=True),
        sa.Column("district", sa.Text, nullable=True),
        sa.Column("state", sa.Text, nullable=True),
        sa.Column("pincode", sa.Text, nullable=True),
        sa.Column("is_default", sa.Boolean, server_default=sa.false(), nullable=False),
        schema="identity",
    )
    op.create_table(
        "preferences",
        pk_column(),
        *timestamp_columns(),
        _user_fk(unique=True),
        sa.Column(
            "notifications", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "privacy", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        schema="identity",
    )


def downgrade() -> None:
    for table in (
        "preferences",
        "addresses",
        "profiles",
        "user_roles",
        "role_permissions",
        "permissions",
        "roles",
        "emails",
        "sessions_refresh",
        "otp_requests",
        "handles_history",
        "users",
    ):
        op.drop_table(table, schema="identity")
    op.execute("DROP SEQUENCE identity.agri_id_seq")
    bind = op.get_bind()
    sa.Enum(name="user_language", schema="identity").drop(bind, checkfirst=True)
    sa.Enum(name="user_status", schema="identity").drop(bind, checkfirst=True)
