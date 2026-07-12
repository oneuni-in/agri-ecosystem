"""D11 profiles+rbac: users.read permission, explicit-only profile language.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-12

"""
# -- THREAT/NOTES:
# downgrade data loss: the users.read permission row and its staff/super_admin
#   grants are deleted; profiles.language NULLs are rewritten to 'en' before
#   NOT NULL is restored, losing the "not chosen yet" state (completion scores
#   are recomputed on the next profile update, so drift self-heals). Acceptable
#   pre-launch.
# locks: single-row DML on tiny RBAC tables; ALTER COLUMN on identity.profiles
#   takes a brief ACCESS EXCLUSIVE lock - the table is small pre-launch.
# rollout: run after 0010. D11 code assumes users.read exists and that
#   profiles.language may be NULL; deploy the migration with (or before) the
#   D11 API code.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = ("users.read", "search users and view their profiles (admin)")
GRANTEE_ROLES = ("staff", "super_admin")

_uuid = postgresql.UUID(as_uuid=True)
permissions_table = sa.table(
    "permissions",
    sa.column("id", _uuid),
    sa.column("name", sa.Text),
    sa.column("description", sa.Text),
    schema="identity",
)
role_permissions_table = sa.table(
    "role_permissions",
    sa.column("id", _uuid),
    sa.column("role_id", _uuid),
    sa.column("permission_id", _uuid),
    schema="identity",
)

language_enum = postgresql.ENUM(
    "en", "ta", "hi", name="user_language", schema="identity", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    permission_id = uuid6.uuid7()
    op.bulk_insert(
        permissions_table,
        [{"id": permission_id, "name": PERMISSION[0], "description": PERMISSION[1]}],
    )
    role_rows = bind.execute(
        sa.text("SELECT id, name FROM identity.roles WHERE name IN :names").bindparams(
            sa.bindparam("names", expanding=True, value=list(GRANTEE_ROLES))
        )
    ).fetchall()
    op.bulk_insert(
        role_permissions_table,
        [
            {"id": uuid6.uuid7(), "role_id": row.id, "permission_id": permission_id}
            for row in role_rows
        ],
    )
    op.alter_column(
        "profiles",
        "language",
        schema="identity",
        existing_type=language_enum,
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE identity.profiles SET language = 'en' WHERE language IS NULL"))
    op.alter_column(
        "profiles",
        "language",
        schema="identity",
        existing_type=language_enum,
        nullable=False,
        server_default=sa.text("'en'"),
    )
    seeded = sa.select(permissions_table.c.id).where(permissions_table.c.name == PERMISSION[0])
    op.execute(
        role_permissions_table.delete().where(role_permissions_table.c.permission_id.in_(seeded))
    )
    op.execute(permissions_table.delete().where(permissions_table.c.name == PERMISSION[0]))
