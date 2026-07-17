"""D17 spec-schema validator: the contract every future vertical rides.
Unknown field rejected, wrong type rejected, version pinning is the
caller's job (service tests) - here the validator itself is hardened."""

import pytest

from modules.directory.specs import (
    MAX_SCHEMA_FIELDS,
    MAX_SPEC_STRING_LEN,
    FieldDef,
    SpecValidationError,
    parse_fields,
    validate_specs,
)

MILK_FIELDS_RAW: list[dict[str, object]] = [
    {
        "key": "milk_type",
        "label": {"en": "Milk type"},
        "type": "enum",
        "options": ["cow", "buffalo", "a2", "toned", "organic"],
        "required": True,
        "filterable": True,
        "facet": True,
        "group": "basics",
    },
    {
        "key": "fat_percent",
        "label": {"en": "Fat %"},
        "type": "number",
        "unit": "%",
        "min": 0,
        "max": 15,
        "filterable": True,
        "comparable": True,
    },
    {
        "key": "pack_size",
        "label": {"en": "Pack size"},
        "type": "enum",
        "options": ["250ml", "500ml", "1l", "5l"],
        "filterable": True,
        "facet": True,
    },
    {"key": "farm_fresh", "label": {"en": "Farm fresh"}, "type": "boolean"},
    {"key": "brand", "label": {"en": "Brand"}, "type": "string"},
]


def fields() -> list[FieldDef]:
    return parse_fields(MILK_FIELDS_RAW)


# --- parse_fields (schema-definition hardening) ---------------------------


def test_parse_valid_fields_roundtrip() -> None:
    parsed = fields()
    assert [f.key for f in parsed] == [
        "milk_type",
        "fat_percent",
        "pack_size",
        "farm_fresh",
        "brand",
    ]


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-list",
        {},
        [{"key": "x"}],  # shape
        [{**MILK_FIELDS_RAW[0], "key": "Bad Key!"}],  # key pattern
        [{**MILK_FIELDS_RAW[0], "type": "json"}],  # unknown type
        [{**MILK_FIELDS_RAW[0], "extra_attr": 1}],  # extra=forbid
        [{**MILK_FIELDS_RAW[0], "label": {"fr": "Lait"}}],  # bad locale
        [{**MILK_FIELDS_RAW[0], "label": {"ta": "பால்"}}],  # missing en
        [{**MILK_FIELDS_RAW[0], "options": None}],  # enum w/o options
        [{**MILK_FIELDS_RAW[0], "options": []}],  # empty options
        [{**MILK_FIELDS_RAW[0], "options": ["a", "a"]}],  # dup options
        [{**MILK_FIELDS_RAW[4], "options": ["x"]}],  # options on non-enum
        [{**MILK_FIELDS_RAW[4], "min": 1}],  # min on non-number
        [{**MILK_FIELDS_RAW[4], "unit": "kg"}],  # unit on non-number
        [{**MILK_FIELDS_RAW[1], "min": 10, "max": 1}],  # min > max
        MILK_FIELDS_RAW + MILK_FIELDS_RAW[:1],  # duplicate key
    ],
)
def test_parse_rejects_bad_definitions(bad: object) -> None:
    with pytest.raises(SpecValidationError) as excinfo:
        parse_fields(bad)
    assert excinfo.value.code == "invalid_field_definition"


def test_parse_rejects_too_many_fields() -> None:
    many = [{**MILK_FIELDS_RAW[4], "key": f"f{i}"} for i in range(MAX_SCHEMA_FIELDS + 1)]
    with pytest.raises(SpecValidationError):
        parse_fields(many)


# --- validate_specs (write-path hardening) --------------------------------


def test_valid_specs_pass_and_normalize() -> None:
    out = validate_specs(
        {"milk_type": "a2", "fat_percent": 4.5, "farm_fresh": True, "brand": "Aavin"}, fields()
    )
    assert out["milk_type"] == "a2"


def test_missing_optional_fields_are_fine() -> None:
    assert validate_specs({"milk_type": "cow"}, fields()) == {"milk_type": "cow"}


@pytest.mark.parametrize(
    "specs,code,field",
    [
        ("not-a-dict", "invalid_specs", None),
        ([1, 2], "invalid_specs", None),
        ({"milk_type": "cow", "hacked": 1}, "unknown_field", "hacked"),  # schema injection
        ({}, "missing_required", "milk_type"),
        ({"milk_type": "goat"}, "invalid_enum_value", "milk_type"),
        ({"milk_type": 3}, "wrong_type", "milk_type"),
        ({"milk_type": "cow", "fat_percent": "high"}, "wrong_type", "fat_percent"),
        (
            {"milk_type": "cow", "fat_percent": True},
            "wrong_type",
            "fat_percent",
        ),  # bool is not number
        ({"milk_type": "cow", "fat_percent": 99}, "out_of_range", "fat_percent"),
        ({"milk_type": "cow", "farm_fresh": "yes"}, "wrong_type", "farm_fresh"),
        ({"milk_type": "cow", "brand": 7}, "wrong_type", "brand"),
        ({"milk_type": "cow", "brand": "x" * (MAX_SPEC_STRING_LEN + 1)}, "too_long", "brand"),
        ({"milk_type": "cow", "brand": {"nested": "obj"}}, "wrong_type", "brand"),
        ({"milk_type": "cow", "fat_percent": float("nan")}, "out_of_range", "fat_percent"),
        ({"milk_type": "cow", "fat_percent": float("inf")}, "out_of_range", "fat_percent"),
        ({"milk_type": "cow", "fat_percent": float("-inf")}, "out_of_range", "fat_percent"),
        ({"milk_type": "cow", "fat_percent": 10**400}, "out_of_range", "fat_percent"),
    ],
)
def test_specs_rejections(specs: object, code: str, field: str | None) -> None:
    with pytest.raises(SpecValidationError) as excinfo:
        validate_specs(specs, fields())
    assert (excinfo.value.code, excinfo.value.field) == (code, field)
