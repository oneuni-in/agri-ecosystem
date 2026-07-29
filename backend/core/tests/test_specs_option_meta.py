"""option_meta (M1): per-enum-option i18n labels + icon key. Presentation
only - parse_fields validates it, validate_specs never reads it."""

import pytest

from modules.directory.specs import SpecValidationError, parse_fields, validate_specs

_META = {"ghee": {"label": {"en": "Ghee", "ta": "நெய்", "hi": "घी"}, "icon": "ghee"}}


def _field(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "key": "category",
        "label": {"en": "Category"},
        "type": "enum",
        "options": ["milk", "ghee"],
        "option_meta": _META,
    }
    base.update(over)
    return base


def test_option_meta_parses_and_round_trips() -> None:
    fields = parse_fields([_field()])
    assert fields[0].option_meta is not None
    meta = fields[0].option_meta["ghee"]
    assert meta.icon == "ghee"
    assert meta.label["ta"] == "நெய்"
    # survives the dump create_schema_version uses to persist fields
    dumped = fields[0].model_dump(exclude_none=True)
    assert dumped["option_meta"]["ghee"]["label"]["hi"] == "घी"


def test_option_meta_is_optional() -> None:
    """Every schema shipped before M1 has no option_meta and stays valid."""
    fields = parse_fields([_field(option_meta=None)])
    assert fields[0].option_meta is None


def test_option_meta_rejected_on_non_enum_field() -> None:
    with pytest.raises(SpecValidationError) as exc:
        parse_fields(
            [{"key": "fat", "label": {"en": "Fat"}, "type": "number", "option_meta": _META}]
        )
    assert exc.value.code == "invalid_field_definition"


def test_option_meta_key_must_be_a_real_option() -> None:
    with pytest.raises(SpecValidationError):
        parse_fields([_field(options=["milk"])])  # meta for "ghee", not an option


def test_option_meta_label_must_include_en() -> None:
    with pytest.raises(SpecValidationError):
        parse_fields([_field(option_meta={"ghee": {"label": {"ta": "நெய்"}, "icon": "ghee"}})])


def test_option_meta_label_rejects_unknown_locale() -> None:
    """The i18n-gap threat closes here: a bad locale never reaches a tile."""
    with pytest.raises(SpecValidationError):
        parse_fields(
            [_field(option_meta={"ghee": {"label": {"en": "Ghee", "xx": "?"}, "icon": "ghee"}})]
        )


def test_validate_specs_ignores_option_meta() -> None:
    """Product writes are unaffected: option_meta takes no part in validation."""
    fields = parse_fields([_field()])
    assert validate_specs({"category": "ghee"}, fields) == {"category": "ghee"}
    with pytest.raises(SpecValidationError) as exc:
        validate_specs({"category": "khoa"}, fields)
    assert exc.value.code == "invalid_enum_value"
