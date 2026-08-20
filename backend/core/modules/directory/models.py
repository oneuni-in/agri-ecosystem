"""Directory module ORM models (D15) - mirrors migrations 0016 + 0017 + 0025 exactly.

owner_user_id is a plain UUID value, never an FK into identity: the module
independence contract forbids directory -> identity coupling at any layer.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import uuid6
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, SoftDeleteMixin, TimestampMixin, UGCMixin, UUIDv7PKMixin
from shared.i18n import Translated, TranslatedString
from shared.slugs import ImmutableSlugMixin

business_type_enum = postgresql.ENUM(
    "vendor", "shop", "lab", "farm", name="business_type", schema="directory", create_type=False
)
business_status_enum = postgresql.ENUM(
    "active", "suspended", "disabled", name="business_status", schema="directory", create_type=False
)
verification_status_enum = postgresql.ENUM(
    "unverified",
    "pending",
    "verified",
    name="verification_status",
    schema="directory",
    create_type=False,
)
subscription_tier_enum = postgresql.ENUM(
    "free", "premium", name="subscription_tier", schema="directory", create_type=False
)


class Business(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, ImmutableSlugMixin, Base):
    __tablename__ = "businesses"
    __table_args__ = {"schema": "directory"}

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Translated | None] = mapped_column(TranslatedString, nullable=True)
    type: Mapped[str] = mapped_column(business_type_enum, nullable=False)
    status: Mapped[str] = mapped_column(
        business_status_enum, nullable=False, server_default="active"
    )
    verification_status: Mapped[str] = mapped_column(
        verification_status_enum, nullable=False, server_default="unverified"
    )
    subscription_tier: Mapped[str] = mapped_column(
        subscription_tier_enum, nullable=False, server_default="free"
    )
    primary_pincode: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # D26: owner-expressed premium intent (activation is server-side only)
    premium_requested_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
    # D26: list of {"days": [...], "open": "HH:MM", "close": "HH:MM"}
    delivery_windows: Mapped[list[dict[str, Any]] | None] = mapped_column(
        postgresql.JSONB, nullable=True
    )
    # M1.5 enforcement soft-state: reason shown to the owner while enforced;
    # prior status restored by reinstate. Both NULL when status='active'.
    enforcement_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    enforcement_prior_status: Mapped[str | None] = mapped_column(
        business_status_enum, nullable=True
    )


class Branch(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "branches"
    __table_args__ = {"schema": "directory"}

    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("directory.businesses.id"),
        nullable=False,
        index=True,
    )
    address: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    district: Mapped[str] = mapped_column(Text, nullable=False)
    pincode: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(Text, nullable=True)
    hours: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="{}"
    )


class Category(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = {"schema": "directory"}

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[Translated] = mapped_column(TranslatedString, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class BusinessCategory(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "business_categories"
    __table_args__ = (
        UniqueConstraint("business_id", "category_id", name="uq_business_categories_pair"),
        {"schema": "directory"},
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("directory.businesses.id"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("directory.categories.id"), nullable=False
    )


class BusinessCoverage(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "business_coverage"
    __table_args__ = (
        UniqueConstraint("business_id", "pincode", name="uq_business_coverage_pair"),
        Index("ix_directory_business_coverage_pincode", "pincode"),
        {"schema": "directory"},
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("directory.businesses.id"), nullable=False
    )
    pincode: Mapped[str] = mapped_column(Text, nullable=False)


class ProfileView(Base):
    """Append-only (BY GRANT) profile-view log (D26 analytics-lite).

    viewer_hash rotates daily (analytics.viewer_hash), so the UNIQUE
    (business_id, viewer_hash) pair enforces 1 view/viewer/business/UTC-day
    without Redis. No timestamp mixin: occurred_at is the only time that
    matters and rows are never updated."""

    __tablename__ = "profile_views"
    __table_args__ = (
        Index(
            "uq_directory_profile_views_dedupe",
            "business_id",
            "viewer_hash",
            unique=True,
        ),
        Index("ix_directory_profile_views_business_occurred", "business_id", "occurred_at"),
        {"schema": "directory"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("directory.businesses.id"), nullable=False
    )
    pincode: Mapped[str | None] = mapped_column(Text, nullable=True)
    viewer_hash: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=False
    )


class Activity(UUIDv7PKMixin, TimestampMixin, Base):
    """ "Live on agri.in" feed row (A-U4b O11) - mirrors migration 0051.

    THE PRIVACY CONTRACT IS THE SCHEMA: no user id, no person's name, no
    pincode, no phone/email column exists, so scrubbing is by construction,
    not by filtering. The only identifying fields are a business's public
    name/slug, nullable so hooks omit them when the business is not
    publicly visible. UNIQUE(kind, source_id) is the house DB-proven
    idempotency idiom - one row per domain happening, ever."""

    __tablename__ = "activity"
    __table_args__ = (
        UniqueConstraint("kind", "source_id", name="uq_directory_activity_kind_source"),
        Index("ix_directory_activity_occurred_at", text("occurred_at DESC")),
        {"schema": "directory"},
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_slug: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


claim_status_enum = postgresql.ENUM(
    "pending", "approved", "rejected", name="claim_status", schema="directory", create_type=False
)
verification_method_enum = postgresql.ENUM(
    "claim", "document", name="verification_method", schema="directory", create_type=False
)


class Claim(UUIDv7PKMixin, TimestampMixin, Base):
    """Ownership claim on a seeded (NULL-owner) business (D16). Decided rows
    are permanent records - no soft delete, no unclaim path (coins-farming
    defence: the award key is claim:{business_id}, once per business ever)."""

    __tablename__ = "claims"
    __table_args__ = (
        Index(
            "uq_directory_claims_one_pending",
            "business_id",
            "claimant_user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_directory_claims_status_id", "status", "id"),
        {"schema": "directory"},
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("directory.businesses.id"), nullable=False
    )
    # plain UUID, never an FK into identity (module independence)
    claimant_user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(claim_status_enum, nullable=False, server_default="pending")
    evidence_docs: Mapped[list[str]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="[]"
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )


report_reason_enum = postgresql.ENUM(
    "fake_listing",
    "wrong_info",
    "abusive",
    "fraud_scam",
    "other",
    name="report_reason",
    schema="directory",
    create_type=False,
)


class Report(UUIDv7PKMixin, TimestampMixin, UGCMixin, Base):
    """User report of a business (M1.5). Ops-Console-only: never rendered on
    any public surface, and the reporter is never revealed to the vendor.
    moderation_status semantics: approved = actioned (admin found it valid;
    enforcement itself is a separate human decision on the business),
    rejected = dismissed."""

    __tablename__ = "reports"
    __table_args__ = (
        # one open report per user per business; re-reportable after a decision
        Index(
            "uq_directory_reports_one_pending",
            "business_id",
            "reporter_user_id",
            unique=True,
            postgresql_where=text("moderation_status = 'pending'"),
        ),
        Index("ix_directory_reports_status_id", "moderation_status", "id"),
        {"schema": "directory"},
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("directory.businesses.id"), nullable=False
    )
    # plain UUID, never an FK into identity (module independence)
    reporter_user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(report_reason_enum, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class Verification(UUIDv7PKMixin, TimestampMixin, Base):
    """Verification-lite record (D16): method='claim' rows are written by
    claim approval; method='document' rows are owner-requested."""

    __tablename__ = "verifications"
    __table_args__ = (
        Index(
            "uq_directory_verifications_one_pending",
            "business_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_directory_verifications_status_id", "status", "id"),
        {"schema": "directory"},
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("directory.businesses.id"), nullable=False
    )
    method: Mapped[str] = mapped_column(verification_method_enum, nullable=False)
    doc_keys: Mapped[list[str]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="[]"
    )
    status: Mapped[str] = mapped_column(claim_status_enum, nullable=False, server_default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
