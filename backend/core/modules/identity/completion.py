"""Profile completion score (D11.B) - pure, no I/O, no clock.

Weights are the spec's confirmed assumption (flagged in the D11 PR): phone 20 /
name 15 / location 25 / language 10 / interests 15 / avatar 15, summing to
exactly 100. Location only counts as the full pincode-derived triple - partial
location never scores. crossed_completion is the single source of truth for
"emit profile.completed exactly once per crossing".
"""

from typing import Final

WEIGHTS: Final[dict[str, int]] = {
    "phone_verified": 20,
    "name": 15,
    "location": 25,
    "language": 10,
    "interests": 15,
    "avatar": 15,
}

COMPLETE_SCORE: Final = 100


def compute_completion(
    *,
    phone_verified: bool,
    has_name: bool,
    has_location: bool,
    has_language: bool,
    has_interests: bool,
    has_avatar: bool,
) -> int:
    present = {
        "phone_verified": phone_verified,
        "name": has_name,
        "location": has_location,
        "language": has_language,
        "interests": has_interests,
        "avatar": has_avatar,
    }
    return sum(weight for part, weight in WEIGHTS.items() if present[part])


def crossed_completion(old_score: int, new_score: int) -> bool:
    """True exactly when an update crosses INTO completeness."""
    return old_score < COMPLETE_SCORE and new_score >= COMPLETE_SCORE
