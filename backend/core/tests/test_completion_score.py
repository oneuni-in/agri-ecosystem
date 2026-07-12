"""D11.B: the score function is pure and table-tested (non-negotiable)."""

import pytest

from modules.identity.completion import (
    COMPLETE_SCORE,
    WEIGHTS,
    compute_completion,
    crossed_completion,
)

_NONE = dict(
    phone_verified=False,
    has_name=False,
    has_location=False,
    has_language=False,
    has_interests=False,
    has_avatar=False,
)


def test_weights_sum_to_complete_score() -> None:
    assert sum(WEIGHTS.values()) == COMPLETE_SCORE == 100


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({}, 0),
        ({"phone_verified": True}, 20),
        ({"has_name": True}, 15),
        ({"has_location": True}, 25),
        ({"has_language": True}, 10),
        ({"has_interests": True}, 15),
        ({"has_avatar": True}, 15),
        ({"phone_verified": True, "has_name": True}, 35),
        ({"phone_verified": True, "has_location": True, "has_language": True}, 55),
        (
            {
                "phone_verified": True,
                "has_name": True,
                "has_location": True,
                "has_language": True,
                "has_interests": True,
            },
            85,
        ),
        (
            {
                "phone_verified": True,
                "has_name": True,
                "has_location": True,
                "has_language": True,
                "has_interests": True,
                "has_avatar": True,
            },
            100,
        ),
    ],
)
def test_score_table(flags: dict[str, bool], expected: int) -> None:
    assert compute_completion(**{**_NONE, **flags}) == expected


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (0, 100, True),
        (85, 100, True),
        (100, 100, False),  # staying complete re-emits nothing
        (85, 85, False),
        (0, 85, False),
        (100, 85, False),  # dropping out of 100 emits nothing
    ],
)
def test_crossing_table(old: int, new: int, expected: bool) -> None:
    assert crossed_completion(old, new) is expected
