"""Identity's contact adapter for shared.lookups (D20). Resolves a user's
notify destination (latest verified email + profile locale) at event-emit
time so billing events stay self-contained (D12 contract). The email is
used once in the event payload and never logged."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Email, Profile
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
