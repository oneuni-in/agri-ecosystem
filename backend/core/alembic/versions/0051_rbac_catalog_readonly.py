# backend/core/alembic/versions/0051_rbac_catalog_readonly.py
"""D12 follow-up: the RBAC catalog stops being writable by the runtime role.

0013 granted app_rt SELECT/INSERT/UPDATE/DELETE on ALL TABLES in eleven
schemas, `identity` among them. That swept in the four RBAC tables, so the
role the API runs as can rewrite the very matrix that decides what the API is
allowed to do. `require_permission` resolves through role_permissions on
every guarded request (identity/rbac.py), so a process that can UPDATE that
table grants itself any permission in the catalog without ever calling an
endpoint. The per-table grants written since 0020 are the house rule; these
four tables predate it and were never brought in line.

Three of the four are pure catalog. roles, permissions and role_permissions
are seeded by migration and only ever read at runtime - nothing in modules/,
shared/ or scripts/ constructs, updates or deletes one; they appear only in
SELECT joins (rbac.py, oauth_service.py, identity/admin_router.py). Revoking
write on them costs the application nothing, which is why this is a grant
change and not a code change.

user_roles keeps INSERT and DELETE, and that is the deliberate part.
Assigning and revoking a user's roles is a real runtime write path:
identity/service.py assign_role inserts, identity/admin_router.py deletes. A
table grant cannot tell the admin console doing that from a compromised
process doing it - `_guard_super_admin` in the router is what draws that
line, and it already does. So this narrows the blast radius from "silently
rewrite the permission matrix" to "assign an existing role", which is the
half the application layer actually guards. It does not claim to close the
second half.

UPDATE on user_roles goes too: an assignment is inserted or deleted, never
edited in place, so the privilege has no caller to break.
"""

# -- THREAT/NOTES:
# - No schema change. No table is created, altered or dropped; this migration
#   only narrows privileges, so no query plan changes and no row is rewritten.
# - locks: REVOKE takes a catalog lock on each table (ACL update). Four short
#   locks, no data pages touched. Safe against a running app.
# - Blast radius if wrong: the API loses a write it needs and the failure is
#   a loud `permission denied`, not silent corruption. Reversible by running
#   the downgrade, which restores exactly the grants 0013 issued.
# - 0013's ALTER DEFAULT PRIVILEGES on `identity` is deliberately left alone.
#   It grants full DML on tables created LATER, which is correct for the rest
#   of the schema (users, sessions, otp state are all runtime-writable). The
#   consequence is that a future RBAC table would inherit DML and need the
#   same revoke; tests/test_rbac_grants.py is what would catch that, since it
#   asserts the matrix per table rather than trusting the default.
# - Fresh databases: 0013 grants the blanket, this revokes it. Order is fixed
#   by the revision chain, so a new DB lands in the same end state as an
#   upgraded one.
# - app_rt is CLUSTER-wide but grants are PER-DATABASE, so this affects only
#   the database it runs against - same standing as every grant since 0013.
# - No PII, no new role, no new enum, no data migration.

from collections.abc import Sequence

from alembic import op

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# seeded by migration, read-only at runtime
CATALOG_TABLES = ("roles", "permissions", "role_permissions")


def upgrade() -> None:
    for table in CATALOG_TABLES:
        op.execute(f"REVOKE INSERT, UPDATE, DELETE ON identity.{table} FROM app_rt")
    # assignments are inserted and deleted, never edited in place
    op.execute("REVOKE UPDATE ON identity.user_roles FROM app_rt")


def downgrade() -> None:
    for table in CATALOG_TABLES:
        op.execute(f"GRANT INSERT, UPDATE, DELETE ON identity.{table} TO app_rt")
    op.execute("GRANT UPDATE ON identity.user_roles TO app_rt")
