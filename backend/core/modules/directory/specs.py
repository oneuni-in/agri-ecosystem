"""Versioned spec-schema validation (D17) - THE contract every vertical
rides. A schema version's `fields` JSONB is parsed by parse_fields();
product specs are validated by validate_specs() on every write against the
version being pinned. Reads never re-validate: old products keep rendering
after a new schema version ships (non-negotiable 1)."""

import math
import re

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from shared.i18n import Translated

MAX_SCHEMA_FIELDS = 50
MAX_SPEC_STRING_LEN = 500
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class SpecValidationError(ValueError):
    """Machine-readable rejection; .code becomes the API 422 detail."""

    def __init__(self, code: str, field: str | None = None) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code}: {field}" if field else code)


class FieldDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: dict[str, str]  # i18n, must include "en" (Translated locales only)
    type: str  # string | number | boolean | enum
    unit: str | None = None  # number fields only
    options: list[str] | None = None  # enum fields only, non-empty, unique
    min: float | None = None  # number fields only
    max: float | None = None
    required: bool = False
    filterable: bool = False
    comparable: bool = False
    facet: bool = False
    group: str | None = None

    @field_validator("key")
    @classmethod
    def _key_shape(cls, v: str) -> str:
        if not _KEY_RE.fullmatch(v):
            raise ValueError(f"bad field key: {v!r}")
        return v

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in ("string", "number", "boolean", "enum"):
            raise ValueError(f"unknown field type: {v!r}")
        return v

    @field_validator("label")
    @classmethod
    def _label_i18n(cls, v: dict[str, str]) -> dict[str, str]:
        Translated.from_dict(v)  # locale allowlist + string values
        if not v.get("en"):
            raise ValueError("label must include en")
        return v

    @model_validator(mode="after")
    def _cross_checks(self) -> "FieldDef":
        if self.type == "enum":
            if not self.options or len(set(self.options)) != len(self.options):
                raise ValueError("enum fields need non-empty unique options")
        elif self.options is not None:
            raise ValueError("options only allowed on enum fields")
        if self.type != "number" and (
            self.min is not None or self.max is not None or self.unit is not None
        ):
            raise ValueError("min/max/unit only allowed on number fields")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min > max")
        return self


def parse_fields(raw: object) -> list[FieldDef]:
    """Validate a schema version's fields payload (admin write path)."""
    if not isinstance(raw, list) or not raw or len(raw) > MAX_SCHEMA_FIELDS:
        raise SpecValidationError("invalid_field_definition")
    parsed: list[FieldDef] = []
    for item in raw:
        try:
            parsed.append(FieldDef.model_validate(item))
        except ValidationError as exc:
            key = item.get("key") if isinstance(item, dict) else None
            raise SpecValidationError("invalid_field_definition", key) from exc
    keys = [f.key for f in parsed]
    if len(set(keys)) != len(keys):
        raise SpecValidationError("invalid_field_definition")
    return parsed


def validate_specs(specs: object, fields: list[FieldDef]) -> dict[str, object]:
    """Validate product specs against a parsed schema version (write path)."""
    if not isinstance(specs, dict):
        raise SpecValidationError("invalid_specs")
    by_key = {f.key: f for f in fields}
    for key in specs:
        if key not in by_key:
            raise SpecValidationError("unknown_field", key)
    for field in fields:
        if field.required and key_missing(specs, field.key):
            raise SpecValidationError("missing_required", field.key)
    for key, value in specs.items():
        _check_value(by_key[key], value)
    return dict(specs)


def key_missing(specs: dict[str, object], key: str) -> bool:
    return key not in specs or specs[key] is None


def _check_value(field: FieldDef, value: object) -> None:
    if field.type == "string":
        if not isinstance(value, str):
            raise SpecValidationError("wrong_type", field.key)
        if len(value) > MAX_SPEC_STRING_LEN:
            raise SpecValidationError("too_long", field.key)
    elif field.type == "boolean":
        if not isinstance(value, bool):
            raise SpecValidationError("wrong_type", field.key)
    elif field.type == "number":
        # bool is an int subclass - reject it explicitly
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise SpecValidationError("wrong_type", field.key)
        if not math.isfinite(value):
            raise SpecValidationError("out_of_range", field.key)
        if (field.min is not None and value < field.min) or (
            field.max is not None and value > field.max
        ):
            raise SpecValidationError("out_of_range", field.key)
    else:  # enum
        if not isinstance(value, str):
            raise SpecValidationError("wrong_type", field.key)
        assert field.options is not None  # guaranteed by FieldDef._cross_checks
        if value not in field.options:
            raise SpecValidationError("invalid_enum_value", field.key)
