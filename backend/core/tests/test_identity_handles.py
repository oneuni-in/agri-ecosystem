"""@handle rules (D06.B): charset/length, reserved blocklist, one free change.

The blocklist exists against handle-squatting of official names (threat
model); the extensible file is how new protected names get added without a
code change.
"""

from pathlib import Path

import pytest

from modules.identity.handles import (
    RESERVED_HANDLES,
    HandleError,
    can_change_handle,
    load_reserved_handles,
    normalize_handle,
    validate_handle,
)

SPEC_BLOCKLIST = (
    "admin",
    "agri",
    "milk",
    "organic",
    "official",
    "support",
    "help",
    "root",
    "api",
    "www",
    "aavin",
    "amul",
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ravi", "ravi"),  # 4 chars: minimum
        ("ravi_farm_2026", "ravi_farm_2026"),
        ("a" * 20, "a" * 20),  # 20 chars: maximum
        ("@ravifarm", "ravifarm"),  # leading @ stripped
        ("RaviFarm", "ravifarm"),  # uppercase input normalized down
        (" ravi ", "ravi"),  # whitespace trimmed
        ("1234", "1234"),  # digits-only is legal
        ("_agri_", "_agri_"),  # underscore placement unrestricted
    ],
)
def test_valid_handles_normalize(raw: str, expected: str) -> None:
    assert validate_handle(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "abc",  # 3 chars: too short
        "a" * 21,  # 21 chars: too long
        "ravi-farm",  # hyphen
        "ravi farm",  # inner space
        "ravi.farm",  # dot
        "ரவி_farm",  # non-ascii
        "ravi🌾",  # emoji
        "AG-0000042",  # fallback-shaped: hyphen keeps namespaces disjoint
    ],
)
def test_invalid_format_rejected(raw: str) -> None:
    with pytest.raises(HandleError) as excinfo:
        validate_handle(raw)
    assert excinfo.value.code == "invalid_format"


@pytest.mark.parametrize("word", SPEC_BLOCKLIST)
def test_every_spec_reserved_word_is_blocked(word: str) -> None:
    with pytest.raises(HandleError) as excinfo:
        validate_handle(word)
    assert excinfo.value.code == "reserved"


@pytest.mark.parametrize("raw", ["Admin", "ADMIN", "@admin", " admin "])
def test_reserved_check_runs_on_the_normalized_form(raw: str) -> None:
    with pytest.raises(HandleError) as excinfo:
        validate_handle(raw)
    assert excinfo.value.code == "reserved"


def test_blocklist_file_contains_the_spec_words() -> None:
    assert set(SPEC_BLOCKLIST) <= RESERVED_HANDLES


def test_blocklist_is_extensible_via_file(tmp_path: Path) -> None:
    extra = tmp_path / "reserved.txt"
    extra.write_text("# comment line\n\nAavinExtra\nnewbrand\n", encoding="utf-8")
    words = load_reserved_handles(extra)
    assert words == frozenset({"aavinextra", "newbrand"})


def test_normalize_handle_is_idempotent() -> None:
    assert normalize_handle(normalize_handle("@RaviFarm")) == "ravifarm"


def test_one_free_change_ever() -> None:
    assert can_change_handle(agri_id_changed_once=False) is True
    assert can_change_handle(agri_id_changed_once=True) is False
