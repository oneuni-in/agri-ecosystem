"""Identity's adapters for shared.lookups (D20).

`notify_contact` resolves a user's notify destination (latest verified email
+ profile locale) at event-emit time so billing events stay self-contained
(D12 contract). The email is used once in the event payload and never logged.

`public_handle` (ID-U1) answers the one question other modules legitimately
have about a user: what do we call them in public? It returns agri_id and
nothing else, so a caller cannot widen its view of a person through this
seam."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Email, Profile, User
from shared.lookups import NotifyContact


async def notify_contact(session: AsyncSession, user_id: uuid.UUID) -> NotifyContact | None:
    email = await session.scalar(
        select(Email.email)
        .where(Email.user_id == user_id, Email.verified_at.is_not(None))
        .order_by(Email.id.desc())
        .limit(1)
    )
    locale = await session.scalar(select(Profile.language).where(Profile.user_id == user_id))
    return NotifyContact(email=email, locale=locale)


async def public_handle(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    """The user's public @handle. Suspended and deleted users resolve to None:
    a name that must not appear on a live surface must not leak through a
    lookup either."""
    handle = await session.scalar(
        select(User.agri_id).where(User.id == user_id, User.status == "active")
    )
    return handle if isinstance(handle, str) else None
