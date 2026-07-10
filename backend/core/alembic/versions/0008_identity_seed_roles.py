"""Seed baseline RBAC: five roles, five permissions, and their grants.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-10

"""
# -- THREAT/NOTES:
# downgrade data loss: deletes exactly the seeded role/permission rows (matched
#   by name) and their grants. user_roles rows pointing at seeded roles are
#   deleted too - acceptable pre-launch; post-launch this downgrade would strip
#   role assignments and must be treated as an incident decision.
# locks: a handful of single-row DML statements on tiny tables; negligible.
# rollout: run after 0007; D07+ code may assume these role names exist.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES: dict[str, str] = {
    "user": "baseline authenticated account",
    "farmer": "verified farming account",
    "business_owner": "verified business account",
    "staff": "internal moderation/support staff",
    "super_admin": "full administrative access",
}

PERMISSIONS: dict[str, str] = {
    "profile.read": "read own profile",
    "profile.write": "edit own profile",
    "handle.change": "change own @handle (one free change)",
    "users.suspend": "suspend or reinstate accounts",
    "roles.assign": "grant or revoke roles",
}

_BASELINE = ("profile.read", "profile.write", "handle.change")
ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    "user": _BASELINE,
    "farmer": _BASELINE,
    "business_owner": _BASELINE,
    "staff": (*_BASELINE, "users.suspend"),
    "super_admin": tuple(PERMISSIONS),
}

_uuid = postgresql.UUID(as_uuid=True)
roles_table = sa.table(
    "roles",
    sa.column("id", _uuid),
    sa.column("name", sa.Text),
    sa.column("description", sa.Text),
    schema="identity",
)
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
user_roles_table = sa.table(
    "user_roles",
    sa.column("role_id", _uuid),
    schema="identity",
)


def upgrade() -> None:
    role_ids = {name: uuid6.uuid7() for name in ROLES}
    permission_ids = {name: uuid6.uuid7() for name in PERMISSIONS}

    op.bulk_insert(
        roles_table,
        [{"id": role_ids[n], "name": n, "description": d} for n, d in ROLES.items()],
    )
    op.bulk_insert(
        permissions_table,
        [{"id": permission_ids[n], "name": n, "description": d} for n, d in PERMISSIONS.items()],
    )
    op.bulk_insert(
        role_permissions_table,
        [
            {"id": uuid6.uuid7(), "role_id": role_ids[role], "permission_id": permission_ids[perm]}
            for role, perms in ROLE_GRANTS.items()
            for perm in perms
        ],
    )


def downgrade() -> None:
    seeded_roles = sa.select(roles_table.c.id).where(roles_table.c.name.in_(list(ROLES)))
    seeded_perms = sa.select(permissions_table.c.id).where(
        permissions_table.c.name.in_(list(PERMISSIONS))
    )
    op.execute(
        role_permissions_table.delete().where(role_permissions_table.c.role_id.in_(seeded_roles))
    )
    op.execute(user_roles_table.delete().where(user_roles_table.c.role_id.in_(seeded_roles)))
    op.execute(
        role_permissions_table.delete().where(
            role_permissions_table.c.permission_id.in_(seeded_perms)
        )
    )
    op.execute(permissions_table.delete().where(permissions_table.c.name.in_(list(PERMISSIONS))))
    op.execute(roles_table.delete().where(roles_table.c.name.in_(list(ROLES))))
