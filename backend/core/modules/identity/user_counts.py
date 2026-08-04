"""Verified-user counts per pincode (M4 contract for shared.geo.tiers).

Lives in identity because identity owns these tables; shared must not
import modules (import-linter), so scripts/geo_tier_nightly.py composes
this with shared.geo.tiers.classify_tiers.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Profile, User


async def verified_user_counts_by_pincode(session: AsyncSession) -> dict[str, int]:
    """Signup-farming defense (threat M4): only phone-verified, active,
    non-deleted users with a server-derived profile pincode count."""
    rows = await session.execute(
        select(Profile.pincode, func.count())
        .join(User, User.id == Profile.user_id)
        .where(
            User.phone_verified_at.is_not(None),
            User.status == "active",
            Profile.pincode.is_not(None),
        )
        .group_by(Profile.pincode)
    )
    return {str(pincode): int(count) for pincode, count in rows}
