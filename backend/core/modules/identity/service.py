"""Identity module public service interface (D06.D) - no HTTP here.

Other modules and future routers (D07+) go through these functions, never
through the tables. Functions take the caller's AsyncSession and flush but
never commit - transaction scope belongs to the caller. The internal UUID
never leaves the service boundary in any public shape (see schemas.py).
"""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.agri_id import AGRI_ID_SEQUENCE, format_agri_id
from modules.identity.models import Role, User, UserRole
from modules.identity.phone import normalize_phone


class UnknownRoleError(LookupError):
    """The requested role name is not seeded/known."""


async def create_user(session: AsyncSession, phone: str) -> User:
    """Create a user with an AG- fallback agri_id from the atomic sequence.

    One account per phone is the users.phone unique constraint; a duplicate
    surfaces as IntegrityError at flush - callers translate, never pre-check.
    """
    normalized = normalize_phone(phone)
    sequence_value = await session.scalar(text(f"SELECT nextval('{AGRI_ID_SEQUENCE}')"))
    if sequence_value is None:  # pragma: no cover - nextval cannot return NULL
        raise RuntimeError("agri_id sequence returned no value")
    user = User(phone=normalized, agri_id=format_agri_id(sequence_value))
    session.add(user)
    await session.flush()
    return user


async def get_by_phone(session: AsyncSession, phone: str) -> User | None:
    return await session.scalar(select(User).where(User.phone == normalize_phone(phone)))


async def assign_role(session: AsyncSession, user_id: uuid.UUID, role_name: str) -> UserRole:
    role = await session.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise UnknownRoleError(role_name)
    user_role = UserRole(user_id=user_id, role_id=role.id)
    session.add(user_role)
    await session.flush()
    return user_role
