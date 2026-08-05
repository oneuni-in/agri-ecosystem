"""Pydantic shapes for the advertiser self-serve API (M5 Task 6).

Every model is `extra="forbid"` - the wire contract for e.g.
`test_client_cannot_set_price` depends on an unknown field (`price_paise`)
being rejected outright rather than silently dropped. All money fields are
server-computed only (modules/ads/pricing.py); nothing here accepts a price
from the client.
"""

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from modules.ads.service import SLOT_KEYS, GeoTargetIn

MAX_CATEGORIES = 20
_CATEGORY_RE = re.compile(r"^[a-z0-9-]{1,40}$")


def _check_categories(value: list[str]) -> list[str]:
    bad = [c for c in value if not _CATEGORY_RE.fullmatch(c)]
    if bad:
        raise ValueError(f"invalid categories: {bad!r}")
    return value


class _QuoteFieldsBase(BaseModel):
    """Shared shape between /quote and campaign create - the wizard sends the
    same targeting/schedule/budget fields to price a campaign and to create
    one. `categories` is a top-level field here (the wizard treats it as its
    own step) even though it lands INSIDE Placement.geo_target on create -
    see selfserve_router._merge_geo_target."""

    slot_keys: Annotated[list[str], Field(min_length=1, max_length=3)]
    geo_target: GeoTargetIn
    categories: Annotated[list[str], Field(max_length=MAX_CATEGORIES)] = Field(default_factory=list)
    flight_start: date
    flight_end: date
    serves_total: Annotated[int, Field(ge=0)] | None = None

    @field_validator("slot_keys")
    @classmethod
    def _slot_keys_known(cls, value: list[str]) -> list[str]:
        bad = [s for s in value if s not in SLOT_KEYS]
        if bad:
            raise ValueError(f"unknown_slot_key: {bad!r}")
        return value

    @field_validator("categories")
    @classmethod
    def _categories_shape(cls, value: list[str]) -> list[str]:
        return _check_categories(value)

    @model_validator(mode="after")
    def _flight_order(self) -> "_QuoteFieldsBase":
        if self.flight_start >= self.flight_end:
            raise ValueError("flight_start must be before flight_end")
        return self


class QuoteIn(_QuoteFieldsBase):
    model_config = ConfigDict(extra="forbid")


class QuoteLineOut(BaseModel):
    label: str
    amount_paise: int


class QuoteOut(BaseModel):
    """Mirror of pricing.Quote - server-computed, never client-suppliable."""

    pricing_model: str
    tier: int
    multiplier_bp: int
    serves_total: int | None
    weeks: int | None
    lines: list[QuoteLineOut]
    subtotal_paise: int
    gst_paise: int
    total_paise: int
    rate_card_version: int


class CampaignCreateIn(_QuoteFieldsBase):
    """target_url is deliberately NOT here - it lives on Creative (Task 8),
    not Campaign; see the task-6 report for the brief deviation."""

    model_config = ConfigDict(extra="forbid")

    business_id: uuid.UUID
    name: Annotated[str, Field(min_length=1, max_length=80)]
    daily_serve_cap: Annotated[int, Field(ge=100)] | None = None


class CampaignPatchIn(BaseModel):
    """Draft-only partial update. Every field is optional; the router reads
    `model_fields_set` to tell "not sent" from "sent as null" and re-quotes
    only when a targeting/schedule/budget field was actually sent. Slot keys
    are fixed at create time - changing slots means delete-the-draft and
    start over (out of scope here)."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    geo_target: GeoTargetIn | None = None
    categories: Annotated[list[str], Field(max_length=MAX_CATEGORIES)] | None = None
    flight_start: date | None = None
    flight_end: date | None = None
    serves_total: Annotated[int, Field(ge=0)] | None = None
    daily_serve_cap: Annotated[int, Field(ge=100)] | None = None

    @field_validator("categories")
    @classmethod
    def _categories_shape(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _check_categories(value)


class PlacementSnapshotOut(BaseModel):
    id: uuid.UUID
    slot_key: str
    geo_target: dict[str, Any]
    status: str


class CreativeSnapshotOut(BaseModel):
    """`ad_copy`/alias="copy": BaseModel already defines `.copy()` (see the
    identical note on modules.ads.schemas.CreativeIn)."""

    id: uuid.UUID
    ad_copy: dict[str, dict[str, str]] = Field(alias="copy")
    media_urls: list[str]
    target_url: str
    moderation_status: str

    model_config = ConfigDict(populate_by_name=True)


class MyCampaignOut(BaseModel):
    id: uuid.UUID
    advertiser_business_id: uuid.UUID
    name: str
    status: str
    # Task 7 owns the real derivation (payment/moderation/budget/flight
    # aware); until then this is a passthrough of the raw status.
    display_status: str
    pricing_model: str | None
    price_paise: int | None
    price_subtotal_paise: int | None
    price_gst_paise: int | None
    rate_card_version: int | None
    budget_serves_total: int | None
    budget_serves_used: int
    daily_serve_cap: int | None
    flight_start: date
    flight_end: date
    created_at: datetime
    placements: list[PlacementSnapshotOut]
    creatives: list[CreativeSnapshotOut]
