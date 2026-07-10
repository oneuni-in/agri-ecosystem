"""E.164 normalization: +91 default for bare Indian mobiles, strict otherwise."""

import pytest

from modules.identity.phone import PhoneError, normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("9876543210", "+919876543210"),  # bare Indian mobile -> +91 default
        ("6000000000", "+916000000000"),  # 6-9 are valid first digits
        ("98765 43210", "+919876543210"),  # separators stripped
        ("98765-43210", "+919876543210"),
        ("(98765)43210", "+919876543210"),
        (" +919876543210 ", "+919876543210"),  # already E.164, whitespace trimmed
        ("+14155552671", "+14155552671"),  # non-Indian E.164 passes through
        ("+1 415 555 2671", "+14155552671"),
    ],
)
def test_normalizes_to_e164(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "12345",  # too short
        "5876543210",  # 10 digits but not a mobile prefix (6-9)
        "98765432100",  # 11 bare digits: ambiguous, rejected
        "+0123456789",  # E.164 cannot start +0
        "+1234",  # too short for E.164 body (needs 8-15 digits total)
        "+123456789012345678",  # too long
        "abcdefghij",
        "98765x3210",
    ],
)
def test_rejects_unnormalizable(raw: str) -> None:
    with pytest.raises(PhoneError):
        normalize_phone(raw)


def test_error_message_never_echoes_the_number() -> None:
    """Exceptions get logged; the raw phone (PII) must not ride along."""
    with pytest.raises(PhoneError) as excinfo:
        normalize_phone("5876543210")
    assert "5876543210" not in str(excinfo.value)
