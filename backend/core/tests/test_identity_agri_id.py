"""AG-XXXXXXX fallback: injective Crockford base32 over an atomic sequence."""

import re

import pytest

from modules.identity.agri_id import (
    AGRI_ID_CAPACITY,
    AGRI_ID_CODE_LENGTH,
    CROCKFORD_ALPHABET,
    encode_crockford,
    format_agri_id,
)


def test_alphabet_is_crockford() -> None:
    """32 symbols; ambiguous I, L, O, U are excluded by Crockford's design."""
    assert len(CROCKFORD_ALPHABET) == 32
    assert len(set(CROCKFORD_ALPHABET)) == 32
    for ambiguous in "ILOU":
        assert ambiguous not in CROCKFORD_ALPHABET


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0000000"),
        (1, "0000001"),
        (31, "000000Z"),
        (32, "0000010"),
        (AGRI_ID_CAPACITY - 1, "ZZZZZZZ"),
    ],
)
def test_encodes_known_values(value: int, expected: str) -> None:
    assert encode_crockford(value) == expected


def test_always_seven_chars_from_the_alphabet() -> None:
    for value in (0, 1, 12345, AGRI_ID_CAPACITY - 1):
        code = encode_crockford(value)
        assert len(code) == AGRI_ID_CODE_LENGTH
        assert set(code) <= set(CROCKFORD_ALPHABET)


def test_injective_over_sample_range() -> None:
    """Distinct inputs -> distinct codes: with the atomic sequence as the only
    input source, collisions are impossible by construction."""
    sample = range(0, 200_000, 7)
    codes = {encode_crockford(value) for value in sample}
    assert len(codes) == len(list(sample))


@pytest.mark.parametrize("value", [-1, AGRI_ID_CAPACITY, AGRI_ID_CAPACITY + 1])
def test_out_of_range_raises(value: int) -> None:
    with pytest.raises(ValueError):
        encode_crockford(value)


def test_format_agri_id() -> None:
    assert format_agri_id(0) == "AG-0000000"
    assert re.fullmatch(r"AG-[0-9A-HJKMNP-TV-Z]{7}", format_agri_id(987654321))


def test_fallback_can_never_be_a_valid_handle() -> None:
    """Uppercase + hyphen means an AG- id can never pass the handle regex,
    so the two public-identity namespaces cannot collide."""
    assert not re.fullmatch(r"[a-z0-9_]{4,20}", format_agri_id(42))
