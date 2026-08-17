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

from sqlalchemy import TIMESTAMP, Date, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, SoftDeleteMixin, TimestampMixin, UUIDv7PKMixin

# A quintal is 100 kg. Agmarknet publishes every price per quintal; the
# cards show per-kg, so this is the ONE conversion in the module.
KG_PER_QUINTAL = Decimal(100)

STATUS_ACTIVE = "active"
STATUS_QUARANTINED = "quarantined"

# Pull outcomes (market.ingest_runs). "empty" is a SUCCESSFUL run that
# found no rows — a fact about the mandi, not a failure of ours.
OUTCOME_OK = "ok"
OUTCOME_EMPTY = "empty"
OUTCOME_FETCH_FAILED = "fetch_failed"
OUTCOME_WRITE_FAILED = "write_failed"
OUTCOME_NO_API_KEY = "no_api_key"
OUTCOME_DISABLED = "disabled"


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


class IngestRun(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One recorded ATTEMPT at a pull — including the ones that fetched
    nothing and the ones that failed (ADR-0012).

    The source serves only the live day, so a day not captured is gone
    permanently. That makes the absence of price rows for a date
    ambiguous forever unless the attempt itself was recorded: a quiet
    Sunday, a job that never fired, and a failed fetch all leave exactly
    the same trace in `price_rows` — none.

    `outcome='empty'` is deliberately NOT `'fetch_failed'`: a successful
    run that found no rows is a fact about the mandi, not about us.
    """

    __tablename__ = "ingest_runs"
    __table_args__ = {"schema": "market"}

    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="agmarknet")
    source_resource: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    state_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    fetched: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    written: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    quarantined: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skipped_uncurated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    newest_arrival_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Scheme(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A government scheme card. `verified_against` + `verified_on` are not
    decoration: the UI renders them, so a card always shows who was checked
    and when."""

    __tablename__ = "schemes"
    __table_args__ = {"schema": "market"}

    level: Mapped[str] = mapped_column(Text, nullable=False)
    state_label: Mapped[dict[str, Any] | None] = mapped_column(postgresql.JSONB, nullable=True)
    title: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    verified_against: Mapped[str] = mapped_column(Text, nullable=False)
    verified_on: Mapped[date] = mapped_column(Date, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    link_label: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class SchemeDeadline(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A deadline chip. `due_on` NULL means a rolling obligation (the 72-hour
    crop-loss intimation applies whenever damage happens); a date means the
    chip stops being served once it has passed, so the page never advertises
    a window that closed."""

    __tablename__ = "scheme_deadlines"
    __table_args__ = {"schema": "market"}

    chip: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    note: Mapped[dict[str, Any] | None] = mapped_column(postgresql.JSONB, nullable=True)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class CropCalendar(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One agro-climatic zone. The month strip is computed at read time from
    `in_season_months`; storing the strip itself would go stale the moment
    the month turned."""

    __tablename__ = "crop_calendars"
    __table_args__ = {"schema": "market"}

    zone_slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    districts: Mapped[list[str]] = mapped_column(postgresql.JSONB, nullable=False)
    in_season_months: Mapped[list[int]] = mapped_column(postgresql.JSONB, nullable=False)
    sowing: Mapped[list[dict[str, Any]]] = mapped_column(postgresql.JSONB, nullable=False)
    harvesting: Mapped[list[dict[str, Any]]] = mapped_column(postgresql.JSONB, nullable=False)
    verified_against: Mapped[str] = mapped_column(Text, nullable=False)
    verified_on: Mapped[date] = mapped_column(Date, nullable=False)


class Msp(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Minimum support price for a curated commodity in a season.

    A number farmers may act on, so it carries the same source + date
    contract as a scheme card and never enters the table unverified.
    """

    __tablename__ = "msp"
    __table_args__ = {"schema": "market"}

    commodity_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("market.commodities.id"), nullable=False
    )
    season: Mapped[str] = mapped_column(Text, nullable=False)
    price_qtl: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    verified_against: Mapped[str] = mapped_column(Text, nullable=False)
    verified_on: Mapped[date] = mapped_column(Date, nullable=False)


class PriceAlert(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A user's standing request for their area's mandi prices.

    Keyed on (user, pincode), not commodity: the home card asks for alerts
    for an AREA, and the daily digest covers whatever curated commodities
    reported in that district.

    `user_id` carries no FK — modules never read identity's tables, so
    notify resolves the recipient from this id at delivery time.
    """

    __tablename__ = "price_alerts"
    __table_args__ = {"schema": "market"}

    user_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    pincode: Mapped[str] = mapped_column(Text, nullable=False)
    # Once-a-day latch: the daily pull is deliberately re-runnable, so
    # without this a retry would notify twice for the same prices.
    last_notified_on: Mapped[date | None] = mapped_column(Date, nullable=True)
