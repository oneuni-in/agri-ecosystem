"""Directory API request/response schemas (D15)."""

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

BusinessType = Literal["vendor", "shop", "lab", "farm"]
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

PINCODE_PATTERN = r"^\d{6}$"
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"

# M1.5.C: About is plain text v1, length-capped. Locale-key validation stays
# in Translated.from_dict (the 400 path test_create_rejects_unknown_locale
# pins); this validator adds the cap + the no-HTML gate as 422s.
ABOUT_MAX_LEN = 2000
_HTML_RE = re.compile(r"<[^>]*>")


def _validate_description(v: dict[str, str] | None) -> dict[str, str] | None:
    if v is None:
        return v
    for key, value in v.items():
        if len(value) > ABOUT_MAX_LEN:
            raise ValueError(f"description[{key}] exceeds {ABOUT_MAX_LEN} characters")
        if _HTML_RE.search(value):
            raise ValueError(f"description[{key}] must be plain text (no HTML)")
    return v


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

    _check_description = field_validator("description")(_validate_description)


class BusinessPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: BusinessType | None = None
    primary_pincode: str | None = Field(default=None, pattern=PINCODE_PATTERN)
    description: dict[str, str] | None = None
    delivery_windows: list[DeliveryWindowIn] | None = Field(default=None, max_length=7)

    _check_description = field_validator("description")(_validate_description)


ReportReason = Literal["fake_listing", "wrong_info", "abusive", "fraud_scam", "other"]


class ReportIn(BaseModel):
    reason: ReportReason
    detail: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _other_requires_detail(self) -> "ReportIn":
        if self.reason == "other" and not self.detail:
            raise ValueError("detail is required when reason is 'other'")
        return self


class ReportCreatedOut(BaseModel):
    """Deliberately opaque: the reporter learns only that the report was
    filed. No report id, no queue position - reports are ops-console-only."""

    status: Literal["pending"] = "pending"


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
    # M1.5: owner-facing while enforced; always None on public surfaces
    # (public reads only ever serve status='active' businesses)
    enforcement_reason: str | None = None


class BusinessPageOut(BaseModel):
    items: list[BusinessOut]
    next_cursor: str | None


class EnforceIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ReinstateIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class AdminBusinessDetailOut(BusinessOut):
    enforcement_prior_status: str | None = None


class EnforcementLogEntryOut(BaseModel):
    id: uuid.UUID
    action: str
    actor_user_id: uuid.UUID | None
    created_at: datetime
    metadata: dict[str, Any] | None


class EnforcementLogPageOut(BaseModel):
    items: list[EnforcementLogEntryOut]
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


class ActiveCategoryOut(CategoryOut):
    """A category with at least one active assigned business (U1b public
    taxonomy read) — the count is how many active businesses carry it."""

    business_count: int


class ActiveCategoryPageOut(BaseModel):
    items: list[ActiveCategoryOut]
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
    # A-U6: the branch a card's Call/WhatsApp tap reveals. An ID, never a
    # number - D18's reveal endpoint is still the only way to a phone, and it
    # is login-gated, daily-capped and DPDP-logged.
    contact_branch_id: uuid.UUID | None = None
    # A-U6: the M3.C organic label, scored by modules/directory/recommended.py
    # - the SAME fn milk-home uses, so the badge cannot mean two things on two
    # sites. Paid signals never enter it. Defaults False so a page that does
    # not ask for the ranking (or a serving error) simply shows no badge.
    recommended: bool = False


class CoversOut(BaseModel):
    items: list[CoversItemOut]
    next_cursor: str | None


class NearbyBranchOut(BaseModel):
    id: uuid.UUID
    address: str
    district: str
    state: str
    pincode: str
    lat: Decimal | None
    lng: Decimal | None
    distance_m: int


class NearbyBranchesOut(BaseModel):
    items: list[NearbyBranchOut]


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


class LiveFeedItemOut(BaseModel):
    """One "Live on agri.in" feed item (A-U4b O11).

    PRIVACY CONTRACT: every field here is either already public elsewhere
    (approved reviews are public, active businesses are listed with their
    name and slug) or coarse by design (district/state - never a pincode).
    NO field identifies a person: there is no user id, no author, no
    contact detail - and none CAN appear, because the backing table
    (directory.activity, migration 0051) has no such columns. Adding a
    field here requires re-checking that contract."""

    kind: Literal["need_posted", "business_joined", "review_approved", "lead_sent"]
    occurred_at: datetime  # serialized ISO-8601
    district: str | None
    state: str | None
    business_name: str | None
    business_slug: str | None
    rating: int | None


class LiveFeedOut(BaseModel):
    items: list[LiveFeedItemOut]
