"""Directory module ORM models (D15) - mirrors migration 0016 exactly.

owner_user_id is a plain UUID value, never an FK into identity: the module
independence contract forbids directory -> identity coupling at any layer.
"""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, SoftDeleteMixin, TimestampMixin, UUIDv7PKMixin
from shared.i18n import Translated, TranslatedString
from shared.slugs import ImmutableSlugMixin

business_type_enum = postgresql.ENUM(
    "vendor", "shop", "lab", "farm", name="business_type", schema="directory", create_type=False
)
business_status_enum = postgresql.ENUM(
    "active", "suspended", name="business_status", schema="directory", create_type=False
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

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
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
        {"schema": "directory"},
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("directory.businesses.id"), nullable=False
    )
    pincode: Mapped[str] = mapped_column(Text, nullable=False, index=True)
