"""Ads ORM models (D21). impressions/clicks are day-partitioned append-only
logs - composite PK (id, occurred_at) because the partition key must be in
the PK; they are never paginated (stats aggregate them instead)."""

import uuid
from datetime import date, datetime
from typing import Any

import uuid6
from sqlalchemy import Date, ForeignKey, Index, Integer, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UGCMixin, UUIDv7PKMixin


class Campaign(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"
    __table_args__ = {"schema": "ads"}

    advertiser_business_id: Mapped[uuid.UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    budget_display: Mapped[str] = mapped_column(Text, server_default="")
    # M3 serve-credit budget: NULL total = unlimited (house ads). `used` only
    # moves through service.consume_budget's atomic conditional UPDATE.
    budget_serves_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    budget_serves_used: Mapped[int] = mapped_column(Integer, server_default="0")
    flight_start: Mapped[date] = mapped_column(Date)
    flight_end: Mapped[date] = mapped_column(Date)
    # M5 self-serve pricing. NULL price_paise = house/admin campaign (never billed).
    # price_paise is the GST-inclusive total; billing invoices read the subtotal/gst
    # decomposition below, never re-derive them.
    pricing_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_subtotal_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_gst_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_card_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    daily_serve_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Creative(UUIDv7PKMixin, UGCMixin, TimestampMixin, Base):
    __tablename__ = "creatives"
    __table_args__ = {"schema": "ads"}

    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.campaigns.id"), index=True)
    media_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    copy: Mapped[dict[str, Any]] = mapped_column(JSONB)
    target_url: Mapped[str] = mapped_column(Text)


class Placement(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "placements"
    __table_args__ = {"schema": "ads"}

    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.campaigns.id"), index=True)
    slot_key: Mapped[str] = mapped_column(Text, index=True)
    geo_target: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    weight: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    status: Mapped[str] = mapped_column(Text, server_default="active")


class _TrackingColumns:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid6.uuid7)
    placement_id: Mapped[uuid.UUID] = mapped_column()
    creative_id: Mapped[uuid.UUID] = mapped_column()
    slot_key: Mapped[str] = mapped_column(Text)
    viewer_hash: Mapped[str] = mapped_column(Text)
    pincode: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)


class DeliveryDecision(UUIDv7PKMixin, Base):
    """M3.E why-served log: append-only BY GRANT + trigger, SAMPLED at serve
    time (settings.ads_delivery_log_sample). viewer_hash is the daily-rotating
    pseudonym - never a user id (threat model: delivery-log PII)."""

    __tablename__ = "delivery_decisions"
    __table_args__ = (
        Index("ix_ads_delivery_decisions_campaign_day", "campaign_id", "occurred_at"),
        {"schema": "ads"},
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column()
    placement_id: Mapped[uuid.UUID] = mapped_column()
    creative_id: Mapped[uuid.UUID] = mapped_column()
    slot_key: Mapped[str] = mapped_column(Text)
    pincode: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    why_served: Mapped[str] = mapped_column(Text)
    viewer_hash: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    # M4: pincode tier at serve time, resolved via shared.geo.service.get_tier
    # (never a direct geo.pincode_tiers read). NULL when the request carried
    # no pincode; DEFAULT_TIER (4) when the pincode is unclassified.
    tier: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class Impression(_TrackingColumns, Base):
    __tablename__ = "impressions"
    __table_args__ = {"schema": "ads"}


class Click(_TrackingColumns, Base):
    __tablename__ = "clicks"
    __table_args__ = {"schema": "ads"}


class RateCardVersion(UUIDv7PKMixin, Base):
    """Append-only pricing config (spec_schemas precedent): change = INSERT version N+1."""

    __tablename__ = "rate_card_versions"
    __table_args__ = {"schema": "ads"}

    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
