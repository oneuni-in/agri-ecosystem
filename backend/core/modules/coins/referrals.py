"""Referral codes + attribution + delayed reward (D13.D). Reward logic is
added in a later step; this file starts with per-user code minting."""

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins.models import ReferralCode

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars


def _mint() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


async def get_or_create_code(session: AsyncSession, user_id: uuid.UUID) -> str:
    existing = await session.scalar(
        select(ReferralCode.code).where(ReferralCode.user_id == user_id)
    )
    if existing is not None:
        return existing
    for _ in range(5):
        code = _mint()
        try:
            async with session.begin_nested():
                session.add(ReferralCode(user_id=user_id, code=code))
                await session.flush()
            return code
        except IntegrityError:
            # unique(code) or unique(user_id) collision; re-read on the latter
            hit = await session.scalar(
                select(ReferralCode.code).where(ReferralCode.user_id == user_id)
            )
            if hit is not None:
                return hit
    raise RuntimeError("could not mint a unique referral code")
