"""Standard mixin columns for hand-written Alembic migrations.

Keep these in lockstep with the ORM mixins in shared/db.py: they are the DDL
face of the same one-way doors. Each call returns fresh Column objects
(a Column can only be attached to one table).

    from shared.migrations import pk_column, soft_delete_column, timestamp_columns, ugc_column

    op.create_table(
        "things",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        ugc_column(),
        sa.Column("name", sa.Text, nullable=False),
        schema="content",
    )
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def pk_column() -> sa.Column[uuid.UUID]:
    """UUIDv7 primary key. Values are generated client-side by the ORM
    (shared.db.UUIDv7PKMixin); raw SQL inserts must supply their own."""
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def timestamp_columns() -> tuple[sa.Column[datetime], sa.Column[datetime]]:
    return (
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def soft_delete_column() -> sa.Column[datetime]:
    return sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True)


def ugc_column() -> sa.Column[str]:
    return sa.Column(
        "moderation_status",
        postgresql.ENUM(
            "pending",
            "approved",
            "rejected",
            name="moderation_status",
            schema="public",
            create_type=False,
        ),
        server_default=sa.text("'pending'"),
        nullable=False,
    )
