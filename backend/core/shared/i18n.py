"""Translated text stored as JSONB {"en", "ta", "hi"}.

Columns declare ``Mapped[Translated] = mapped_column(TranslatedString)``;
Python code always sees a Translated value with a fallback chain
(requested locale -> en -> any non-empty).
"""

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import Dialect, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB

SUPPORTED_LOCALES = ("en", "ta", "hi")


@dataclass(frozen=True, slots=True)
class Translated:
    en: str | None = None
    ta: str | None = None
    hi: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Translated":
        unknown = set(raw) - set(SUPPORTED_LOCALES)
        if unknown:
            raise ValueError(f"unsupported locale keys: {sorted(unknown)}")
        bad_values = [key for key, value in raw.items() if not isinstance(value, str)]
        if bad_values:
            raise ValueError(f"non-string translations for: {sorted(bad_values)}")
        return cls(**raw)

    def to_dict(self) -> dict[str, str]:
        return {key: value for key, value in asdict(self).items() if value is not None}

    def get(self, locale: str) -> str | None:
        """Requested locale, else English, else any non-empty translation."""
        if locale not in SUPPORTED_LOCALES:
            raise ValueError(f"unsupported locale: {locale!r}")
        for candidate in (getattr(self, locale), self.en, self.ta, self.hi):
            if candidate:
                return candidate
        return None


class TranslatedString(TypeDecorator[Translated]):
    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value: object, dialect: Dialect) -> dict[str, str] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            value = Translated.from_dict(value)
        if not isinstance(value, Translated):
            raise TypeError(f"expected Translated or dict, got {type(value).__name__}")
        return value.to_dict()

    def process_result_value(self, value: object, dialect: Dialect) -> Translated | None:
        if value is None:
            return None
        assert isinstance(value, dict)
        return Translated.from_dict(value)
