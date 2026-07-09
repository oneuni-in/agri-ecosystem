"""geo schema v1: states, districts, pincode centroids.

LGD (Local Government Directory) codes are the natural keys - they are
stable across district renames, which the display names are not.
"""

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Text
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
