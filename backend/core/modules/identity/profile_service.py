"""Progressive profile updates + completion recompute (D11.A/B) - no HTTP.

Location is pincode-driven: clients send a pincode, the server derives
district/state from the D03 geo snapshot - free-text location is never
trusted (profiles.state/district are plain Text with no FK; this service is
the only writer). Progressive v1: fields are set, never cleared.

Functions take the caller's AsyncSession and flush but never commit.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.completion import (
    compute_completion,
    crossed_completion,
    missing_parts,
)
from modules.identity.models import FarmProfile, Preference, Profile, User
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


def _completion_flags(user: User, profile: Profile | None) -> dict[str, bool]:
    """One reading of the profile, shared by the score and the missing list so
    the bar and the line beside it can never disagree (ID-U1 P7)."""
    return {
        "phone_verified": user.phone_verified_at is not None,
        "has_name": bool(profile is not None and profile.name),
        "has_location": bool(
            profile is not None and profile.state and profile.district and profile.pincode
        ),
        "has_language": profile is not None and profile.language is not None,
        "has_interests": bool(profile is not None and profile.interests),
        "has_avatar": profile is not None and profile.avatar_key is not None,
    }


def live_score(user: User, profile: Profile | None) -> int:
    return compute_completion(**_completion_flags(user, profile))


def live_missing(user: User, profile: Profile | None) -> list[str]:
    """Which parts are still empty, heaviest first - what the completion bar's
    "what's missing" line renders."""
    return missing_parts(**_completion_flags(user, profile))


async def recompute_score(
    session: AsyncSession, *, user: User, profile: Profile
) -> tuple[int, bool]:
    """Persist the recomputed score; True iff this update crossed into 100."""
    old = profile.completion_score
    new = live_score(user, profile)
    profile.completion_score = new
    await session.flush()
    return new, crossed_completion(old, new)


# --- ID-U1 W5: the farm profile ---------------------------------------------

DESCRIBES_VALUES = ("farmer", "business", "exploring")
LAND_UNITS = ("acres", "hectares")
TENURES = ("owned", "leased", "both")
IRRIGATION = ("borewell", "canal", "rainfed")

# A guard, not a product limit. Nobody enters six digits of cattle by hand, and
# without a ceiling a fat-fingered paste becomes a number every future advisory
# has to defend itself against.
LIVESTOCK_MAX = 100_000
LAND_AREA_MAX = Decimal("99999.99")


def normalize_describes(values: list[str]) -> list[str]:
    """Deduped, ordered, and restricted to the known set.

    Order is DESCRIBES_VALUES' order rather than the order tapped, so two
    people who picked the same two things store the same list.
    """
    chosen = {value.strip().lower() for value in values}
    unknown = chosen - set(DESCRIBES_VALUES)
    if unknown:
        raise ProfileUpdateError("invalid_describes")
    # "exploring" is the answer "neither", so it cannot be combined with one
    if "exploring" in chosen and len(chosen) > 1:
        raise ProfileUpdateError("invalid_describes")
    return [value for value in DESCRIBES_VALUES if value in chosen]


async def get_farm_profile(session: AsyncSession, user_id: uuid.UUID) -> FarmProfile | None:
    row = await session.scalar(select(FarmProfile).where(FarmProfile.user_id == user_id))
    return row if isinstance(row, FarmProfile) else None


async def apply_farm_profile(
    session: AsyncSession, user_id: uuid.UUID, patch: dict[str, object]
) -> FarmProfile:
    """Progressive, and CLEARABLE - unlike the rest of the profile.

    Everywhere else in this module an omitted field means "leave it alone" and
    nothing can be emptied (scores only rise, crossings fire once). Farm data
    is different: a farmer who sells their cattle has to be able to say so, and
    a field that can only ever be set would make the profile a record of what
    was once true. So an explicit null here CLEARS. Omission still means "leave
    it alone" - the two are distinguishable because the caller sends only the
    keys it means.
    """
    row = await get_farm_profile(session, user_id)
    if row is None:
        row = FarmProfile(user_id=user_id)
        session.add(row)
    for field in ("land_unit", "tenure", "irrigation"):
        if field not in patch:
            continue
        value = patch[field]
        allowed = {"land_unit": LAND_UNITS, "tenure": TENURES, "irrigation": IRRIGATION}[field]
        if value is not None and value not in allowed:
            raise ProfileUpdateError(f"invalid_{field}")
        setattr(row, field, value)
    for field in ("cattle", "goats", "poultry"):
        if field not in patch:
            continue
        value = patch[field]
        if value is not None and (not isinstance(value, int) or not 0 <= value <= LIVESTOCK_MAX):
            raise ProfileUpdateError(f"invalid_{field}")
        setattr(row, field, value)
    if "land_area" in patch:
        area = patch["land_area"]
        if area is not None:
            try:
                area = Decimal(str(area))
            except (ArithmeticError, ValueError) as exc:
                raise ProfileUpdateError("invalid_land_area") from exc
            if area < 0 or area > LAND_AREA_MAX:
                raise ProfileUpdateError("invalid_land_area")
        row.land_area = area
    # land_unit without land_area is meaningless, and land_area without a unit
    # is a number nobody can act on - a scheme threshold in hectares cannot
    # read "3.5".
    if row.land_area is not None and row.land_unit is None:
        row.land_unit = "acres"
    await session.flush()
    return row
