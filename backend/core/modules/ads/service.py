"""Ads service (D21): validation + (Task 8) serving eligibility."""

import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLOT_KEYS: frozenset[str] = frozenset({"directory_browse"})
MAX_TARGET_URL = 2048
LOCALES = ("en", "ta", "hi")

_PINCODE_RE = re.compile(r"^\d{6}$")


def validate_target_url(url: str) -> None:
    """Ad-as-XSS gate: http/https absolute URLs only (no javascript:, data:,
    scheme-relative or fragment tricks). Called at creative create AND at
    serve time (defense in depth - a bad row must still never reach a page)."""
    if len(url) > MAX_TARGET_URL:
        raise ValueError("target_url too long")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("target_url must be an absolute http(s) URL")


class GeoTargetIn(BaseModel):
    """{} means serve everywhere; unknown keys are rejected outright."""

    model_config = ConfigDict(extra="forbid")

    state: int | None = None
    district: int | None = None
    pincodes: list[str] | None = Field(default=None, max_length=50)

    @field_validator("pincodes")
    @classmethod
    def _pincode_shape(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        bad = [p for p in value if not _PINCODE_RE.fullmatch(p)]
        if bad:
            raise ValueError(f"invalid pincodes: {bad!r}")
        return value
