"""Identity service skeleton (D06.D): create_user / get_by_phone / assign_role.
Service interface only - no HTTP, no commits (transaction scope is the caller's)."""

import re
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Role, UserRole
from modules.identity.service import UnknownRoleError, assign_role, create_user, get_by_phone

AGRI_ID_PATTERN = re.compile(r"^AG-[0-9A-HJKMNP-TV-Z]{7}$")


async def test_create_user_assigns_ag_fallback(db_session: AsyncSession) -> None:
    user = await create_user(db_session, "9876543210")
    assert user.phone == "+919876543210"  # +91 default applied
    assert AGRI_ID_PATTERN.fullmatch(user.agri_id)
    assert user.agri_id_changed_once is False


async def test_agri_ids_are_distinct(db_session: AsyncSession) -> None:
    first = await create_user(db_session, "9876543210")
    second = await create_user(db_session, "9876543211")
    assert first.agri_id != second.agri_id


async def test_one_account_per_phone_bubbles_integrity_error(db_session: AsyncSession) -> None:
    await create_user(db_session, "9876543210")
    with pytest.raises(IntegrityError):
        await create_user(db_session, "+91 98765 43210")  # same number, different spelling


async def test_get_by_phone_normalizes_before_lookup(db_session: AsyncSession) -> None:
    created = await create_user(db_session, "+919876543210")
    found = await get_by_phone(db_session, "98765 43210")
    assert found is not None
    assert found.id == created.id


async def test_get_by_phone_returns_none_for_unknown(db_session: AsyncSession) -> None:
    assert await get_by_phone(db_session, "9876543299") is None


async def test_assign_role_links_seeded_role(db_session: AsyncSession) -> None:
    user = await create_user(db_session, "9876543210")
    link = await assign_role(db_session, user.id, "farmer")

    role = await db_session.scalar(select(Role).where(Role.id == link.role_id))
    assert role is not None and role.name == "farmer"
    stored = await db_session.scalar(select(UserRole).where(UserRole.user_id == user.id))
    assert stored is not None


async def test_assign_unknown_role_raises(db_session: AsyncSession) -> None:
    user = await create_user(db_session, "9876543210")
    with pytest.raises(UnknownRoleError):
        await assign_role(db_session, user.id, "warlord")


async def test_assign_role_to_missing_user_bubbles_integrity_error(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(IntegrityError):
        await assign_role(db_session, uuid.uuid4(), "user")
