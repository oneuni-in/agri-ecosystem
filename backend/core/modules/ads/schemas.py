"""Pydantic shapes for the ads admin routes (D21). Creatives land pending -
approval is the unified moderation queue's job (Task 7), never this router's."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from modules.ads.service import LOCALES, GeoTargetIn, validate_target_url

CampaignStatus = Literal["draft", "active", "paused", "archived"]
PlacementStatus = Literal["active", "paused"]
# M5 reconciliation: CampaignStatus above is the ADMIN-settable set, which
# still predates the 8-state self-serve lifecycle. For a PRICED campaign only
# these three are admissible - notably NOT `draft`, which would let staff push
# a paid, live campaign back into the editable state the advertiser can
# re-quote from, desyncing price/budget from an AdOrder + ledger row + an
# already-emailed invoice. `active` stays in the set but keeps its own
# payment-AND-moderation gate (decision 14) in admin_router.
PAID_CAMPAIGN_STATUSES = frozenset({"active", "paused", "archived"})

MAX_CREATIVE_MEDIA = 5
MAX_COPY_TITLE = 120
MAX_COPY_BODY = 500


class CopyBlock(BaseModel):
    """One locale's ad text. Plain strings only - never markup/HTML."""

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=MAX_COPY_TITLE)]
    body: Annotated[str, Field(min_length=1, max_length=MAX_COPY_BODY)]


class CampaignIn(BaseModel):
    advertiser_business_id: uuid.UUID
    name: Annotated[str, Field(min_length=1)]
    budget_display: str = ""
    # M3 serve-credit ceiling; None = unlimited. Money stays in billing (M5).
    budget_serves_total: Annotated[int, Field(ge=0)] | None = None
    flight_start: date
    flight_end: date

    @model_validator(mode="after")
    def _flight_order(self) -> "CampaignIn":
        if self.flight_start >= self.flight_end:
            raise ValueError("flight_start must be before flight_end")
        return self


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    advertiser_business_id: uuid.UUID
    name: str
    status: str
    budget_display: str
    budget_serves_total: int | None
    budget_serves_used: int
    flight_start: date
    flight_end: date
    # M5: a self-serve campaign is priced and paid for. Staff need to see BOTH
    # here or the admin listing gives no hint that a campaign carries real
    # money (and that admin_router's paid-campaign status guard applies to
    # it). NULL price_paise == house/admin campaign, never billed.
    price_paise: int | None
    paid_at: datetime | None
    created_at: datetime


class CampaignPageOut(BaseModel):
    items: list[CampaignOut]
    next_cursor: str | None


class StatusIn(BaseModel):
    status: CampaignStatus


class CreativeIn(BaseModel):
    # `ad_copy` not `copy`: BaseModel already defines a `.copy()` method (the
    # v1 shallow-copy helper, still present in v2) and mypy --strict flags
    # any field that redefines it with an incompatible type. `alias="copy"`
    # keeps the wire contract exactly as specced (JSON key `copy` in/out).
    campaign_id: uuid.UUID
    media_keys: Annotated[list[str], Field(max_length=MAX_CREATIVE_MEDIA)] = Field(
        default_factory=list
    )
    ad_copy: dict[str, CopyBlock] = Field(alias="copy")
    target_url: str

    @field_validator("ad_copy")
    @classmethod
    def _copy_locales(cls, value: dict[str, CopyBlock]) -> dict[str, CopyBlock]:
        unknown = set(value) - set(LOCALES)
        if unknown:
            raise ValueError(f"unsupported locale keys: {sorted(unknown)}")
        if "en" not in value:
            raise ValueError("copy must include en")
        return value

    @field_validator("target_url")
    @classmethod
    def _target_url(cls, value: str) -> str:
        validate_target_url(value)  # raises ValueError -> 422
        return value


class CreativeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    media_keys: list[str]
    ad_copy: dict[str, dict[str, str]] = Field(alias="copy")
    target_url: str
    moderation_status: str
    created_at: datetime


class CreativePageOut(BaseModel):
    items: list[CreativeOut]
    next_cursor: str | None


class PlacementIn(BaseModel):
    campaign_id: uuid.UUID
    slot_key: str
    geo_target: GeoTargetIn = Field(default_factory=GeoTargetIn)
    weight: int = 1


class PlacementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    slot_key: str
    geo_target: dict[str, object]
    weight: int
    status: str
    created_at: datetime


class PlacementPageOut(BaseModel):
    items: list[PlacementOut]
    next_cursor: str | None


class PlacementStatusIn(BaseModel):
    status: PlacementStatus


def copy_to_json(ad_copy: dict[str, CopyBlock]) -> dict[str, dict[str, str]]:
    """CreativeIn.ad_copy (validated CopyBlock models) -> plain JSONB-ready dict."""
    return {locale: block.model_dump() for locale, block in ad_copy.items()}


class ServedAdOut(BaseModel):
    """Wire contract for a served ad. `label` is always the literal
    "sponsored" - non-negotiable 1, enforced at the type level."""

    placement_id: uuid.UUID
    creative_id: uuid.UUID
    slot_key: str
    label: Literal["sponsored"]
    title: str
    body: str
    media_urls: list[str]
    target_url: str


class AdServeOut(BaseModel):
    ad: ServedAdOut | None  # legacy single-ad shape (D21 web-agri mount)
    ads: list[ServedAdOut] = []  # M2 carousel: weighted, distinct placements


class BeaconIn(BaseModel):
    """Wire contract for both tracking beacons (impressions/clicks). No
    location - beacons are joined to serve-side geo data later in analysis."""

    placement_id: uuid.UUID
    creative_id: uuid.UUID
    slot_key: str


class BeaconOut(BaseModel):
    status: Literal["ok", "duplicate"]


class StatRowOut(BaseModel):
    """One day's impression and click counts for a placement."""

    day: date
    impressions: int
    clicks: int


class StatsOut(BaseModel):
    """Per-placement daily impression/click stats."""

    rows: list[StatRowOut]


class PerfRowOut(BaseModel):
    """Impressions, clicks and CTR for one slot or one creative (U3 read
    surface). `ctr` is the plain ratio clicks/impressions (0.0 when no
    impressions) — a display metric, never a money figure."""

    key: str
    impressions: int
    clicks: int
    ctr: float


class PerfOut(BaseModel):
    """Ad performance from the M2/M3 beacons, broken down two ways."""

    by_slot: list[PerfRowOut]
    by_creative: list[PerfRowOut]


class RateCardIn(BaseModel):
    """M5 Task 3: Ops-submitted rate card config. Shape is validated by
    pricing.validate_rate_card, not here - config is an opaque dict at the
    wire level so pricing.py stays the single source of truth for the shape."""

    config: dict[str, Any]


class RateCardOut(BaseModel):
    version: int
    config: dict[str, Any]
    created_at: datetime
