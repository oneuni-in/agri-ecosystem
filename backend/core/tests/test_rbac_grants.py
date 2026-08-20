# backend/core/tests/test_rbac_grants.py
"""The runtime role must not be able to rewrite the RBAC catalog.

0013 gave app_rt a blanket SELECT/INSERT/UPDATE/DELETE on every table in
`identity` (a per-schema GRANT plus ALTER DEFAULT PRIVILEGES, so tables added
later inherit it). Three of the four RBAC tables - roles, permissions,
role_permissions - are catalog: seeded by migration and only ever SELECTed at
runtime (rbac.py and oauth_service.py join them; nothing anywhere constructs,
updates or deletes one). Leaving them writable means an app-level compromise
can widen an existing role's permission set without ever calling the API.

user_roles is deliberately NOT locked down. The admin console assigns and
revokes roles at runtime (identity/service.py assign_role inserts,
admin_router deletes), so app_rt keeps INSERT and DELETE there. A grant cannot
tell an admin action from a compromised one - `_guard_super_admin` in the
router is what gates that, and this file asserts the capability survives so a
future tightening cannot silently break role assignment.
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

CATALOG_TABLES = ("roles", "permissions", "role_permissions")

# Every statement is a no-op (`WHERE false` / `SELECT ... WHERE false`) so the
# test can never mutate the catalog it is guarding. Postgres checks the table
# ACL when the plan starts, not per row, so a revoked grant still raises.
FORBIDDEN_STATEMENTS = (
    "INSERT INTO identity.roles (id, name) SELECT gen_random_uuid(), '__pwn__' WHERE false",
    "UPDATE identity.roles SET name = '__pwn__' WHERE false",
    "DELETE FROM identity.roles WHERE false",
    "INSERT INTO identity.permissions (id, name) SELECT gen_random_uuid(), '__pwn__' WHERE false",
    "UPDATE identity.permissions SET name = '__pwn__' WHERE false",
    "DELETE FROM identity.permissions WHERE false",
    "INSERT INTO identity.role_permissions (id, role_id, permission_id) "
    "SELECT gen_random_uuid(), gen_random_uuid(), gen_random_uuid() WHERE false",
    "UPDATE identity.role_permissions SET role_id = gen_random_uuid() WHERE false",
    "DELETE FROM identity.role_permissions WHERE false",
)


@pytest.fixture
async def runtime_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """Engine on the app's real runtime identity (app_rt), not the owner."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.mark.parametrize("statement", FORBIDDEN_STATEMENTS)
async def test_app_rt_cannot_write_rbac_catalog(
    runtime_engine: AsyncEngine, statement: str
) -> None:
    # a fresh connection per statement: a permission error aborts the
    # transaction, which would poison any statement sharing it
    async with runtime_engine.connect() as conn:
        with pytest.raises((ProgrammingError, DBAPIError)) as excinfo:
            await conn.execute(text(statement))
    assert "permission denied" in str(excinfo.value).lower()


@pytest.mark.parametrize("table", CATALOG_TABLES)
async def test_rbac_catalog_is_select_only_for_app_rt(
    runtime_engine: AsyncEngine, table: str
) -> None:
    async with runtime_engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = 'app_rt' AND table_schema = 'identity' "
                "AND table_name = :table"
            ),
            {"table": table},
        )
    assert {row[0] for row in rows} == {"SELECT"}


async def test_app_rt_can_still_assign_and_revoke_user_roles(
    runtime_engine: AsyncEngine,
) -> None:
    """Guards the fix from over-revoking: role assignment is a real runtime
    write path, so user_roles must keep INSERT and DELETE.

    UPDATE is revoked because an assignment is never edited in place - it is
    inserted (service.assign_role) or deleted (admin_router). Keeping UPDATE
    would only widen what a compromised process can do.
    """
    async with runtime_engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT has_table_privilege('app_rt', 'identity.user_roles', 'SELECT') AS sel, "
                "has_table_privilege('app_rt', 'identity.user_roles', 'INSERT') AS ins, "
                "has_table_privilege('app_rt', 'identity.user_roles', 'DELETE') AS del, "
                "has_table_privilege('app_rt', 'identity.user_roles', 'UPDATE') AS upd"
            )
        )
    assert rows.one() == (True, True, True, False)
