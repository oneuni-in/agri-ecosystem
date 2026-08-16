"""Agmarknet feed -> market.price_rows, with the quality gate (A-U2 W2).

Three checks stand between a government feed and a farmer's screen:

  1. CURATION. Only commodities in market.commodities are ingested. A
     feed row for something nobody has named in three locales is counted
     and skipped, never auto-created.
  2. SANITY. min <= modal <= max, and no non-positive price. A row that
     fails is QUARANTINED, not dropped: ops can see what arrived.
  3. OUTLIERS. A modal price at or beyond `mandi_outlier_factor` times
     the trailing median for that commodity+market — in EITHER direction
     — is quarantined. This is the defence against a misplaced decimal
     reaching a price card, and a decimal is as likely to divide by ten
     as to multiply by it. Where a market has no history of its own the
     comparison widens to the commodity across all markets rather than
     skipping: the source serves only the live day, so a row waved
     through now can never be revalidated later (ADR-0012).

Quarantined rows keep their reason and are never returned by a read path
that feeds the site.

Idempotency is the natural-key unique constraint from 0038: re-running a
pull updates in place. That is what makes the daily job safe to re-run
and a partial failure safe to retry.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from settings import get_settings
from shared.telemetry import get_logger

from .agmarknet import PriceRecord
from .models import STATUS_ACTIVE, STATUS_QUARANTINED, Commodity, Market, PriceRow

logger = get_logger(__name__)


@dataclass
class IngestResult:
    fetched: int = 0
    written: int = 0
    quarantined: int = 0
    skipped_uncurated: int = 0
    # The newest arrival_date the batch carried, or None for an empty
    # batch. Recorded on the run ledger so "did we ever hold 16 Aug?"
    # stays answerable even when every row was skipped as uncurated.
    newest_arrival_date: date | None = None

    def as_dict(self) -> dict[str, int]:
        return {
            "fetched": self.fetched,
            "written": self.written,
            "quarantined": self.quarantined,
            "skipped_uncurated": self.skipped_uncurated,
        }


def _slugify(name: str) -> str:
    """Same rule as modules/directory/service.py's, reimplemented rather
    than imported: modules never import each other, and this is four
    lines of regex, not a shared abstraction worth a seam."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base or "market"


def _sanity_reason(record: PriceRecord) -> str | None:
    if min(record.min_price_qtl, record.max_price_qtl, record.modal_price_qtl) <= 0:
        return "non_positive_price"
    if record.min_price_qtl > record.max_price_qtl:
        return "min_above_max"
    if not (record.min_price_qtl <= record.modal_price_qtl <= record.max_price_qtl):
        return "modal_outside_range"
    return None


async def _commodity_index(session: AsyncSession) -> dict[str, Commodity]:
    rows = (await session.scalars(select(Commodity))).all()
    # Matched case-insensitively: the feed's spelling has drifted before,
    # and a case change upstream must not silently orphan a commodity.
    return {row.agmarknet_name.casefold(): row for row in rows}


async def _market_for(session: AsyncSession, record: PriceRecord) -> Market:
    existing = await session.scalar(
        select(Market).where(
            Market.state == record.state,
            Market.district == record.district,
            Market.name == record.market,
        )
    )
    if existing is not None:
        return existing
    market = Market(
        slug=_slugify(f"{record.market}-{record.district}"),
        name=record.market,
        state=record.state,
        district=record.district,
    )
    session.add(market)
    await session.flush()
    return market


async def _trailing_median(
    session: AsyncSession,
    commodity_id: uuid.UUID,
    market_id: uuid.UUID | None,
    before: date,
) -> Decimal | None:
    """Median modal price in the trailing window, or None if no history.

    `market_id=None` widens the comparison to the same commodity across
    every market — used only when this market has no history of its own
    (see _outlier_reason). The candidate row is never in its own
    comparison set: the window ends strictly before its arrival date.
    """
    settings = get_settings()
    window_start = before - timedelta(days=settings.mandi_median_window_days)
    conditions = [
        PriceRow.commodity_id == commodity_id,
        PriceRow.status == STATUS_ACTIVE,
        PriceRow.arrival_date >= window_start,
        PriceRow.arrival_date < before,
    ]
    if market_id is not None:
        conditions.append(PriceRow.market_id == market_id)
    values = (await session.scalars(select(PriceRow.modal_price_qtl).where(*conditions))).all()
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


# Reason codes by (comparison basis, direction). Ops reads these, so the
# basis is part of the code: "quarantined against this market's own
# history" and "quarantined against the commodity across all markets" are
# different levels of confidence and must not look identical.
_OUTLIER_REASONS = {
    ("market", "high"): "outlier_vs_median",
    ("market", "low"): "outlier_below_median",
    ("commodity", "high"): "outlier_vs_commodity_median",
    ("commodity", "low"): "outlier_below_commodity_median",
}


async def _outlier_reason(
    session: AsyncSession,
    commodity_id: uuid.UUID,
    market_id: uuid.UUID,
    record: PriceRecord,
) -> str | None:
    """Quarantine reason for an implausible price, or None.

    TWO-SIDED ON PURPOSE. A misplaced decimal is as likely to divide by
    ten as to multiply by it, and Rs 2400/qtl published as Rs 240 renders
    a Rs 2.40/kg card where Rs 24.00 belongs. That passes every sanity
    check — min <= modal <= max still holds when all three shift together
    — so the median comparison is the only thing standing in front of it.
    A price that looks like a market collapse is at least as damaging to
    someone deciding whether to cart a load in as one that looks like a
    spike.

    FIRST-ROW FALLBACK. A commodity+market pair with no history has no
    median to compare against, and markets are created from the feed
    continuously, so this is not a one-time day-one condition. Because
    the source only serves the live day, an unchecked row can never be
    revalidated later. So the check widens to the same commodity across
    every market rather than waving the row through: mandi prices for one
    commodity differ between markets, but not by an order of magnitude.
    """
    settings = get_settings()
    factor = Decimal(str(settings.mandi_outlier_factor))
    if factor <= 1:  # a factor of 1 or less would quarantine everything
        return None

    basis = "market"
    median = await _trailing_median(session, commodity_id, market_id, record.arrival_date)
    if median is None:
        basis = "commodity"
        median = await _trailing_median(session, commodity_id, None, record.arrival_date)
    if median is None or median <= 0:
        # Genuinely nothing to compare against. The row is accepted and the
        # run ledger (market.ingest_runs) is what records that this day was
        # ingested at all — see ADR-0012.
        return None

    # >= and <=, not > and <: the classic misplaced decimal lands EXACTLY
    # on the factor, so strict comparisons would wave through the very
    # error these checks exist to catch.
    if record.modal_price_qtl >= median * factor:
        return _OUTLIER_REASONS[(basis, "high")]
    if record.modal_price_qtl * factor <= median:
        return _OUTLIER_REASONS[(basis, "low")]
    return None


async def ingest_records(session: AsyncSession, records: list[PriceRecord]) -> IngestResult:
    """Write a fetched batch. Safe to re-run: the natural key upserts."""
    result = IngestResult(
        fetched=len(records),
        newest_arrival_date=max((r.arrival_date for r in records), default=None),
    )
    commodities = await _commodity_index(session)

    for record in records:
        commodity = commodities.get(record.commodity.casefold())
        if commodity is None:
            result.skipped_uncurated += 1
            continue

        market = await _market_for(session, record)

        reason = _sanity_reason(record)
        if reason is None:
            reason = await _outlier_reason(session, commodity.id, market.id, record)

        status = STATUS_QUARANTINED if reason else STATUS_ACTIVE
        if reason:
            result.quarantined += 1
        else:
            result.written += 1

        values = {
            "commodity_id": commodity.id,
            "market_id": market.id,
            "arrival_date": record.arrival_date,
            "variety": record.variety,
            "grade": record.grade,
            "min_price_qtl": record.min_price_qtl,
            "max_price_qtl": record.max_price_qtl,
            "modal_price_qtl": record.modal_price_qtl,
            "status": status,
            "quarantine_reason": reason,
            "source": "agmarknet",
            "source_resource": "9ef84268-d588-465a-a308-a864a43d0070",
        }
        statement = pg_insert(PriceRow).values(**values)
        await session.execute(
            statement.on_conflict_do_update(
                constraint="uq_price_rows_natural_key",
                # A corrected republication should win; the natural key
                # is what keeps that an update instead of a duplicate.
                set_={
                    "min_price_qtl": statement.excluded.min_price_qtl,
                    "max_price_qtl": statement.excluded.max_price_qtl,
                    "modal_price_qtl": statement.excluded.modal_price_qtl,
                    "status": statement.excluded.status,
                    "quarantine_reason": statement.excluded.quarantine_reason,
                },
            )
        )

    logger.info("market.mandi_ingested", extra={"extra_fields": result.as_dict()})
    return result
