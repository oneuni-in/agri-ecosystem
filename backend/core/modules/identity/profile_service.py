"""Progressive profile updates + completion recompute (D11.A/B) - no HTTP.

Location is pincode-driven: clients send a pincode, the server derives
district/state from the D03 geo snapshot - free-text location is never
trusted (profiles.state/district are plain Text with no FK; this service is
the only writer). Progressive v1: fields are set, never cleared.

Functions take the caller's AsyncSession and flush but never commit.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.completion import compute_completion, crossed_completion
from modules.identity.models import Preference, Profile, User
from shared.geo.models import State
from shared.geo.service import district_for_pincode

INTERESTS_MAX = 10
INTEREST_CHAR_MAX = 40
VISIBILITY_KEYS = frozenset({"name", "location", "language", "interests", "avatar"})


class ProfileUpdateError(ValueError):
    """Rejected update; .code is the API error detail."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def get_or_create_profile(session: AsyncSession, user_id: uuid.UUID) -> Profile:
    profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None:
        profile = Profile(user_id=user_id, language=None)
        session.add(profile)
        await session.flush()
    return profile


def normalize_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name:
        raise ProfileUpdateError("empty_name")
    return name


def normalize_interests(raw: list[str]) -> list[str]:
    """Free-form v1 (confirmed assumption): trim, collapse whitespace,
    case-insensitive dedupe preserving first spelling, caps enforced."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = " ".join(item.split())
        if not text:
            raise ProfileUpdateError("empty_interest")
        if len(text) > INTEREST_CHAR_MAX:
            raise ProfileUpdateError("interest_too_long")
        if text.lower() in seen:
            continue
        seen.add(text.lower())
        cleaned.append(text)
    if len(cleaned) > INTERESTS_MAX:
        raise ProfileUpdateError("too_many_interests")
    return cleaned


async def apply_location(session: AsyncSession, profile: Profile, pincode: str) -> None:
    district = await district_for_pincode(session, pincode)
    if district is None:
        raise ProfileUpdateError("unknown_pincode")
    state = await session.scalar(select(State).where(State.id == district.state_id))
    assert state is not None  # FK guarantees the parent row
    profile.pincode = pincode
    profile.district = district.name
    profile.state = state.name


async def get_visibility(session: AsyncSession, user_id: uuid.UUID) -> dict[str, bool]:
    """Private-by-default: absent keys read as False. Phone and email are not
    keys at all - they are never public (non-negotiable), not a toggle."""
    preference = await session.scalar(select(Preference).where(Preference.user_id == user_id))
    stored = preference.privacy if preference is not None else {}
    return {key: bool(stored.get(key, False)) for key in sorted(VISIBILITY_KEYS)}


async def set_visibility(
    session: AsyncSession, user_id: uuid.UUID, toggles: dict[str, bool]
) -> None:
    unknown = set(toggles) - VISIBILITY_KEYS
    if unknown:
        raise ProfileUpdateError("unknown_visibility_key")
    preference = await session.scalar(select(Preference).where(Preference.user_id == user_id))
    if preference is None:
        preference = Preference(user_id=user_id, notifications={}, privacy={})
        session.add(preference)
    preference.privacy = {**preference.privacy, **{k: bool(v) for k, v in toggles.items()}}
    await session.flush()


def live_score(user: User, profile: Profile | None) -> int:
    return compute_completion(
        phone_verified=user.phone_verified_at is not None,
        has_name=bool(profile is not None and profile.name),
        has_location=bool(
            profile is not None and profile.state and profile.district and profile.pincode
        ),
        has_language=profile is not None and profile.language is not None,
        has_interests=bool(profile is not None and profile.interests),
        has_avatar=profile is not None and profile.avatar_key is not None,
    )


async def recompute_score(
    session: AsyncSession, *, user: User, profile: Profile
) -> tuple[int, bool]:
    """Persist the recomputed score; True iff this update crossed into 100."""
    old = profile.completion_score
    new = live_score(user, profile)
    profile.completion_score = new
    await session.flush()
    return new, crossed_completion(old, new)
