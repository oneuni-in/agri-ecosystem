"""Ads ORM models (D21). impressions/clicks are day-partitioned append-only
logs - composite PK (id, occurred_at) because the partition key must be in
the PK; they are never paginated (stats aggregate them instead)."""

import uuid
from datetime import date, datetime
from typing import Any

import uuid6
from sqlalchemy import Date, ForeignKey, SmallInteger, Text
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
    flight_start: Mapped[date] = mapped_column(Date)
    flight_end: Mapped[date] = mapped_column(Date)


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


class Impression(_TrackingColumns, Base):
    __tablename__ = "impressions"
    __table_args__ = {"schema": "ads"}


class Click(_TrackingColumns, Base):
    __tablename__ = "clicks"
    __table_args__ = {"schema": "ads"}
