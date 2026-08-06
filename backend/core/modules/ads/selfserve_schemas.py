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

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

from modules.ads.schemas import CopyBlock
from modules.ads.service import LOCALES, GeoTargetIn

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

    # Membership in service.SLOT_KEYS is NOT checked here - the router
    # validates it explicitly (HTTPException(422, "unknown_slot_key")) so the
    # wire contract matches the sibling admin route (modules/ads/admin_router
    # .create_placement) exactly: a plain string in `detail`, not a pydantic
    # structured error list.
    slot_keys: Annotated[list[str], Field(min_length=1, max_length=3)]
    geo_target: GeoTargetIn
    categories: Annotated[list[str], Field(max_length=MAX_CATEGORIES)] = Field(default_factory=list)
    flight_start: date
    flight_end: date
    serves_total: Annotated[int, Field(ge=0)] | None = None

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


class CreativeCopyIn(RootModel[dict[str, CopyBlock]]):
    """Task 8: the multipart `copy_json` form field on the creative
    upload/edit routes, parsed with `json.loads` then validated here through
    the SAME locale rules as admin's `CreativeIn._copy_locales`
    (modules/ads/schemas.py) - en required, keys restricted to LOCALES.
    Reused (via CopyBlock) rather than duplicated; only the locale-set
    check itself needs re-stating because a RootModel has no natural home
    for a field_validator on its own root."""

    @model_validator(mode="after")
    def _copy_locales(self) -> "CreativeCopyIn":
        unknown = set(self.root) - set(LOCALES)
        if unknown:
            raise ValueError(f"unsupported locale keys: {sorted(unknown)}")
        if "en" not in self.root:
            raise ValueError("copy must include en")
        return self


class CreativeSnapshotOut(BaseModel):
    """`ad_copy`/alias="copy": BaseModel already defines `.copy()` (see the
    identical note on modules.ads.schemas.CreativeIn)."""

    id: uuid.UUID
    ad_copy: dict[str, dict[str, str]] = Field(alias="copy")
    media_urls: list[str]
    target_url: str
    moderation_status: str

    model_config = ConfigDict(populate_by_name=True)


class StatsDayRow(BaseModel):
    day: date
    impressions: int
    clicks: int


class StatsKeyCount(BaseModel):
    """One bucket of `ads.delivery_decisions` GROUP BY key. `key` is the raw
    pincode/category/tier value, string-coerced; `"unknown"` stands in for a
    NULL (no pincode/category context, or no resolvable tier)."""

    key: str
    serves: int


class CampaignStatsOut(BaseModel):
    """Advertiser campaign analytics (M5 Task 13). `impressions`/`clicks`/
    `ctr_bp`/`by_day` are exact (drawn from ads.impressions/ads.clicks, keyed
    by placement_id - never sampled). `by_pincode`/`by_category`/`by_tier`
    come from ads.delivery_decisions, each capped at the top 20 rows by
    serve count (bounded payload, not a full breakdown) - see `sampled`.

    `spend_paise` is LEDGER-CAPPED (Task 13 fast-follow, closing a reported
    correctness bug): it starts from a DERIVED estimate off the campaign's
    pricing snapshot and current budget counters (cpm: proportional to
    serve-credits consumed; flat_weekly: full price once paid), then is
    capped at `charged_net_paise` (shared.lookups.resolve_campaign_charged -
    billing's own append-only ledger, charges positive/refunds negative)
    whenever that resolver answers a number. This matters because a refund
    overwrites `budget_serves_total := budget_serves_used` as a
    serve-exhaustion trick (Task 7/10), not a real budget - deriving spend
    from that column alone would report 100% of price spent FOREVER on a
    refunded campaign. `charged_net_paise` is `None` when billing has no
    ledger rows at all for this campaign (house/unpaid - the derived
    estimate is used as-is) or when the resolver isn't registered
    (fail-closed the same way); it is exactly 0 after a full refund, which
    is what pins `spend_paise` to 0 too. A refunded campaign's `spend_paise`
    therefore reports the RETAINED amount, not the original price."""

    days: int
    serves_used: int
    serves_total: int | None
    spend_paise: int
    charged_net_paise: int | None
    impressions: int
    clicks: int
    ctr_bp: int
    by_day: list[StatsDayRow]
    by_pincode: list[StatsKeyCount]
    by_category: list[StatsKeyCount]
    by_tier: list[StatsKeyCount]
    # False for priced campaigns: M5 Task 13 makes `log_delivery(always=True)`
    # bypass sampling for every campaign with price_paise set, so
    # by_pincode/by_category/by_tier are a complete count of delivery
    # decisions going forward. True for house/admin campaigns (price_paise is
    # NULL - still sampled at settings.ads_delivery_log_sample). NOTE: rows
    # logged for a priced campaign BEFORE this change shipped may still be
    # sampled - `sampled` reflects the current logging policy, not a
    # per-row guarantee for historical data.
    sampled: bool


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
