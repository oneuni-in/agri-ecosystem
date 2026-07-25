"""Directory API request/response schemas (D15)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

BusinessType = Literal["vendor", "shop", "lab", "farm"]
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

PINCODE_PATTERN = r"^\d{6}$"
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class DeliveryWindowIn(BaseModel):
    days: list[Weekday] = Field(min_length=1, max_length=7)
    open: str = Field(pattern=TIME_PATTERN)
    close: str = Field(pattern=TIME_PATTERN)

    @model_validator(mode="after")
    def _open_before_close(self) -> "DeliveryWindowIn":
        if self.open >= self.close:  # HH:MM strings compare lexicographically
            raise ValueError("open must be before close (overnight windows unsupported)")
        return self


class BusinessCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: BusinessType
    primary_pincode: str = Field(pattern=PINCODE_PATTERN)
    description: dict[str, str] | None = None


class BusinessPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: BusinessType | None = None
    primary_pincode: str | None = Field(default=None, pattern=PINCODE_PATTERN)
    description: dict[str, str] | None = None
    delivery_windows: list[DeliveryWindowIn] | None = Field(default=None, max_length=7)


class RenameIn(BaseModel):
    new_slug: str = Field(pattern=SLUG_PATTERN, min_length=3, max_length=80)


class TierSelectionIn(BaseModel):
    tier: Literal["free", "premium"]


class TierSelectionOut(BaseModel):
    subscription_tier: str
    premium_requested_at: datetime | None


class BusinessOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    type: str
    status: str
    verification_status: str
    subscription_tier: str
    claimable: bool
    primary_pincode: str
    description: dict[str, str] | None
    delivery_windows: list[dict[str, Any]] | None
    created_at: datetime


class BusinessPageOut(BaseModel):
    items: list[BusinessOut]
    next_cursor: str | None


class BranchCreateIn(BaseModel):
    address: str = Field(min_length=1)
    state: str = Field(min_length=1)
    district: str = Field(min_length=1)
    pincode: str = Field(pattern=PINCODE_PATTERN)
    lat: Decimal | None = None
    lng: Decimal | None = None
    phone: str | None = None
    whatsapp: str | None = None
    hours: dict[str, Any] = Field(default_factory=dict)


class BranchPatchIn(BaseModel):
    address: str | None = Field(default=None, min_length=1)
    state: str | None = Field(default=None, min_length=1)
    district: str | None = Field(default=None, min_length=1)
    pincode: str | None = Field(default=None, pattern=PINCODE_PATTERN)
    lat: Decimal | None = None
    lng: Decimal | None = None
    phone: str | None = None
    whatsapp: str | None = None
    hours: dict[str, Any] | None = None


class BranchOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    address: str
    state: str
    district: str
    pincode: str
    lat: Decimal | None
    lng: Decimal | None
    phone: str | None
    whatsapp: str | None
    hours: dict[str, Any]


class PublicBranchOut(BaseModel):
    """Branch as served on the PUBLIC detail page - contact fields are
    structurally absent (D18.C): reveal is a separate capped endpoint."""

    id: uuid.UUID
    business_id: uuid.UUID
    address: str
    state: str
    district: str
    pincode: str
    lat: Decimal | None
    lng: Decimal | None
    hours: dict[str, Any]


class CoverageIn(BaseModel):
    pincodes: list[str] = Field(max_length=500)


class CoverageOut(BaseModel):
    pincodes: list[str]


class CategoryOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: dict[str, str]
    sort_order: int


class CategoryPageOut(BaseModel):
    items: list[CategoryOut]
    next_cursor: str | None


class CategoryAssignIn(BaseModel):
    category_ids: list[uuid.UUID] = Field(max_length=50)


class CategoryAssignOut(BaseModel):
    category_ids: list[uuid.UUID]


class BusinessDetailOut(BaseModel):
    business: BusinessOut
    branches: list[PublicBranchOut]
    categories: list[CategoryOut]
    coverage_pincodes: list[str]


class CoversItemOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    type: str
    verification_status: str
    subscription_tier: str
    primary_pincode: str
    distance_m: int
    lat: Decimal | None
    lng: Decimal | None


class CoversOut(BaseModel):
    items: list[CoversItemOut]
    next_cursor: str | None


ClaimStatus = Literal["pending", "approved", "rejected"]


class ClaimOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    claimant_user_id: uuid.UUID
    status: str
    evidence_count: int
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None


class ClaimPageOut(BaseModel):
    items: list[ClaimOut]
    next_cursor: str | None


class VerificationOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    method: str
    status: str
    notes: str | None
    doc_count: int
    created_at: datetime
    decided_at: datetime | None


class VerificationPageOut(BaseModel):
    items: list[VerificationOut]
    next_cursor: str | None


class AdminClaimOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    business_name: str
    claimant_user_id: uuid.UUID
    status: str
    evidence_count: int
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None


class AdminClaimPageOut(BaseModel):
    items: list[AdminClaimOut]
    next_cursor: str | None


class AdminVerificationOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    business_name: str
    method: str
    status: str
    notes: str | None
    doc_count: int
    created_at: datetime
    decided_at: datetime | None


class AdminVerificationPageOut(BaseModel):
    items: list[AdminVerificationOut]
    next_cursor: str | None


class DecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class RejectIn(BaseModel):
    note: str = Field(min_length=3, max_length=1000)  # reject always carries a reason


class AdminTierIn(BaseModel):
    tier: Literal["free", "premium"]


class ViewBeaconIn(BaseModel):
    pincode: str | None = Field(default=None, pattern=PINCODE_PATTERN)


class ViewBeaconOut(BaseModel):
    status: str


class PincodeCountOut(BaseModel):
    pincode: str
    count: int


class AnalyticsSectionOut(BaseModel):
    total: int
    by_pincode: list[PincodeCountOut]


class AnalyticsResponseOut(BaseModel):
    total: int
    responded: int
    avg_response_seconds: int | None


class BusinessAnalyticsOut(BaseModel):
    days: int
    views: AnalyticsSectionOut
    reveals: AnalyticsSectionOut
    leads: AnalyticsSectionOut
    response: AnalyticsResponseOut
