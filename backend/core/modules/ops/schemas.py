"""Ops Console wire schemas (D21)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from shared.moderation import ModItem


class ModItemOut(BaseModel):
    type_key: str
    id: uuid.UUID
    created_at: datetime
    title: str
    summary: str
    payload: dict[str, object]


def item_out(item: ModItem) -> ModItemOut:
    return ModItemOut(
        type_key=item.type_key,
        id=item.id,
        created_at=item.created_at,
        title=item.title,
        summary=item.summary,
        payload=item.payload,
    )


class ModQueuePageOut(BaseModel):
    items: list[ModItemOut]
    next_cursor: str | None = None


class ModerationSummaryOut(BaseModel):
    counts: dict[str, int]


class DecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ModRejectIn(BaseModel):
    note: str = Field(min_length=1, max_length=500)


class FlagOut(BaseModel):
    key: str
    enabled: bool
    description: str
    updated_at: datetime


class FlagsOut(BaseModel):
    items: list[FlagOut]


class FlagToggleIn(BaseModel):
    enabled: bool


class PincodeTierOut(BaseModel):
    pincode: str
    tier: int
    population: int
    # census input (town / village / district_apportioned) — surfaced so the
    # computed tier can be sanity-checked before KYC (U3 read surface).
    population_grade: str
    user_count: int
    method: str
    computed_at: datetime | None
    tier_changed_at: datetime | None


class PincodeTierPageOut(BaseModel):
    items: list[PincodeTierOut]
    next_cursor: str | None = None


class TierBucketOut(BaseModel):
    tier: int
    count: int


class TierDistributionOut(BaseModel):
    buckets: list[TierBucketOut]  # always 5 entries, T1..T5
    by_method: dict[str, int]
    unclassified: int
    total: int


class TierOverrideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: int = Field(ge=1, le=5)
