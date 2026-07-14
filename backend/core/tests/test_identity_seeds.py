"""Seed migration 0008: the five roles and baseline permissions exist after
upgrade, wired via role_permissions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Permission, Role, RolePermission

EXPECTED_ROLES = {"user", "farmer", "business_owner", "staff", "super_admin"}
EXPECTED_PERMISSIONS = {
    "profile.read",
    "profile.write",
    "handle.change",
    "users.suspend",
    "roles.assign",
    "users.read",
    "coins.rules.write",
    "coins.adjust",
    "coins.abuse.review",
}


async def test_roles_seeded(db_session: AsyncSession) -> None:
    names = set((await db_session.scalars(select(Role.name))).all())
    assert names >= EXPECTED_ROLES


async def test_permissions_seeded(db_session: AsyncSession) -> None:
    names = set((await db_session.scalars(select(Permission.name))).all())
    assert names >= EXPECTED_PERMISSIONS


async def test_super_admin_has_every_baseline_permission(db_session: AsyncSession) -> None:
    stmt = (
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name == "super_admin")
    )
    granted = set((await db_session.scalars(stmt)).all())
    assert granted == EXPECTED_PERMISSIONS


async def test_plain_user_cannot_suspend_or_assign(db_session: AsyncSession) -> None:
    stmt = (
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name == "user")
    )
    granted = set((await db_session.scalars(stmt)).all())
    assert granted == {"profile.read", "profile.write", "handle.change"}


async def test_staff_can_read_and_suspend_but_not_assign(db_session: AsyncSession) -> None:
    stmt = (
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name == "staff")
    )
    granted = set((await db_session.scalars(stmt)).all())
    assert granted == {
        "profile.read",
        "profile.write",
        "handle.change",
        "users.suspend",
        "users.read",
        "coins.abuse.review",
    }
