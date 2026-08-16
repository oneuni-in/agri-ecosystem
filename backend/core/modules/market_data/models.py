"""Market Data ORM models (A-U2 W2). Tables land in 0038.

Prices are stored exactly as Agmarknet publishes them — rupees per
quintal, as NUMERIC — and converted for display at read time, so a
stored row always matches its source.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import TIMESTAMP, Date, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, SoftDeleteMixin, TimestampMixin, UUIDv7PKMixin

# A quintal is 100 kg. Agmarknet publishes every price per quintal; the
# cards show per-kg, so this is the ONE conversion in the module.
KG_PER_QUINTAL = Decimal(100)

STATUS_ACTIVE = "active"
STATUS_QUARANTINED = "quarantined"


class Commodity(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Curated, not open-ended: a commodity exists here because someone
    wrote its three-locale name and picked its emoji. Feed rows for
    anything else are counted and skipped, never auto-created with an
    untranslated name."""

    __tablename__ = "commodities"
    __table_args__ = {"schema": "market"}

    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    emoji: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    display_unit: Mapped[str] = mapped_column(Text, nullable=False, server_default="kg")
    agmarknet_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class Market(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A mandi as the feed names it. Place names from a government
    source, so English-only by design — inventing Tamil spellings for
    them would be fabrication, not translation."""

    __tablename__ = "markets"
    __table_args__ = {"schema": "market"}

    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    district: Mapped[str] = mapped_column(Text, nullable=False)


class PriceRow(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One published price for a commodity in a market on a date.

    `status` is a DATA-QUALITY flag, not a moderation state: these are
    public records, not user content. A quarantined row stays in the
    table with its reason so ops can see what the feed sent; no read
    path that feeds the site ever returns it.
    """

    __tablename__ = "price_rows"
    __table_args__ = {"schema": "market"}

    commodity_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("market.commodities.id"), nullable=False
    )
    market_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("market.markets.id"), nullable=False
    )
    arrival_date: Mapped[date] = mapped_column(Date, nullable=False)
    variety: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    grade: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    min_price_qtl: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    max_price_qtl: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    modal_price_qtl: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=STATUS_ACTIVE)
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="agmarknet")
    source_resource: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    ingested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


def per_kg(price_qtl: Decimal) -> float:
    """Rupees per quintal -> rupees per kg, the figure the cards show."""
    return float(round(price_qtl / KG_PER_QUINTAL, 2))
