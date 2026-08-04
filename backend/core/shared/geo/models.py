"""geo schema v1: states, districts, pincode centroids.

LGD (Local Government Directory) codes are the natural keys - they are
stable across district renames, which the display names are not.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import TIMESTAMP, BigInteger, ForeignKey, Integer, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UUIDv7PKMixin


class State(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "states"
    __table_args__ = {"schema": "geo"}

    lgd_code: Mapped[int] = mapped_column(unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_ta: Mapped[str | None] = mapped_column(Text, nullable=True)


class District(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "districts"
    __table_args__ = {"schema": "geo"}

    lgd_code: Mapped[int] = mapped_column(unique=True, nullable=False)
    state_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("geo.states.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_ta: Mapped[str | None] = mapped_column(Text, nullable=True)


class Pincode(UUIDv7PKMixin, TimestampMixin, Base):
    """One row per pincode; the centroid averages its post-office locations."""

    __tablename__ = "pincodes"
    __table_args__ = {"schema": "geo"}

    pincode: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    district_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("geo.districts.id"), nullable=False, index=True
    )
    centroid_lat: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    centroid_lon: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)


class PincodeTier(UUIDv7PKMixin, TimestampMixin, Base):
    """Automatic T1-T5 classification per pincode (M4).

    No FK to geo.pincodes: pan-India rows exist here while geo.pincodes
    stays TN-only (Stage-B dormancy). computed_at NULL = loaded from the
    population snapshot but never classified; tier defaults to 4, the same
    safe default get_tier() returns for a missing row.
    """

    __tablename__ = "pincode_tiers"
    __table_args__ = {"schema": "geo"}

    pincode: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    population: Mapped[int] = mapped_column(BigInteger, nullable=False)
    population_grade: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="4")
    user_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    computed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    tier_changed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    method: Mapped[str] = mapped_column(Text, nullable=False, server_default="population")


class PincodeTierHistory(UUIDv7PKMixin, Base):
    """Append-only audit of tier changes (M4). created_at only - an
    updated_at column on an immutable table would be a lie (per 0013, which
    itself uses func.now()). This table's created_at uses clock_timestamp()
    instead of now(): a single classify_tiers() run inserts many history
    rows in one transaction, and now() is frozen per-transaction, so every
    row would get an identical timestamp; clock_timestamp() advances within
    the transaction, giving each insert a distinct, orderable time."""

    __tablename__ = "pincode_tier_history"
    __table_args__ = {"schema": "geo"}

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    pincode: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    old_tier: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    new_tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    old_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_method: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
