"""A-U2 W2 — Agmarknet parsing, the quality gate, and the mandi read.

The fixture rows below are REAL records captured from data.gov.in
resource 9ef84268-… on 2026-08-16, so the parser is tested against the
shape the feed actually publishes (DD/MM/YYYY dates, rupees per quintal,
"Paddy(Common)" with no space, and no arrivals column at all).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.market_data.agmarknet import parse_record
from modules.market_data.ingest import ingest_records
from modules.market_data.models import STATUS_QUARANTINED, PriceRow, per_kg
from modules.market_data.service import get_mandi
from shared.flags import FeatureFlag, reset_flag_cache

from .d26_helpers import api  # noqa: F401 — the shared client fixture

pytestmark = pytest.mark.anyio

# Verbatim from the live feed.
LIVE_ROWS: list[dict[str, Any]] = [
    {
        "state": "Andhra Pradesh",
        "district": "Tirupathi",
        "market": "Vakadu APMC",
        "commodity": "Paddy(Common)",
        "variety": "B P T",
        "grade": "Local",
        "arrival_date": "16/08/2026",
        "min_price": 2389,
        "max_price": 2410,
        "modal_price": 2400,
    },
    {
        "state": "Andhra Pradesh",
        "district": "Sri Sathya Sai",
        "market": "Dharmavaram APMC",
        "commodity": "Groundnut",
        "variety": "Local",
        "grade": "FAQ",
        "arrival_date": "16/08/2026",
        "min_price": 7000,
        "max_price": 7200,
        "modal_price": 7100,
    },
    {
        # Curated set does not include Bengal Gram -> counted, skipped.
        "state": "Andhra Pradesh",
        "district": "Markapuram",
        "market": "Markapur APMC",
        "commodity": "Bengal Gram(Gram)(Whole)",
        "variety": "Desi (Whole)",
        "grade": "FAQ",
        "arrival_date": "16/08/2026",
        "min_price": 5450,
        "max_price": 5450,
        "modal_price": 5450,
    },
]


def _row(**overrides: Any) -> dict[str, Any]:
    base = dict(LIVE_ROWS[0])
    base.update(overrides)
    return base


def _records(rows: list[dict[str, Any]]) -> list[Any]:
    parsed = [parse_record(row) for row in rows]
    return [record for record in parsed if record is not None]


# ── parsing ──────────────────────────────────────────────────────────


def test_parses_a_real_feed_row() -> None:
    record = parse_record(LIVE_ROWS[0])
    assert record is not None
    assert record.commodity == "Paddy(Common)"
    assert record.arrival_date == date(2026, 8, 16)  # DD/MM/YYYY, not ISO
    assert record.modal_price_qtl == Decimal("2400")


def test_unusable_rows_are_skipped_not_fatal() -> None:
    assert parse_record(_row(arrival_date="2026-08-16")) is None  # wrong format
    assert parse_record(_row(modal_price=None)) is None
    assert parse_record(_row(market="")) is None


def test_quintal_to_kg_is_the_only_conversion() -> None:
    # Paddy at Rs 2400/quintal is Rs 24.00/kg — the figure the card shows.
    assert per_kg(Decimal("2400")) == 24.0
    assert per_kg(Decimal("7100")) == 71.0


# ── quality gate ─────────────────────────────────────────────────────


async def test_ingest_curates_and_counts(db_session: AsyncSession) -> None:
    result = await ingest_records(db_session, _records(LIVE_ROWS))
    assert result.fetched == 3
    assert result.written == 2
    assert result.skipped_uncurated == 1  # Bengal Gram is not curated
    assert result.quarantined == 0


async def test_ingest_is_idempotent(db_session: AsyncSession) -> None:
    """Re-running a day must update in place, never duplicate — this is
    what makes the daily job safe to re-run."""
    records = _records(LIVE_ROWS)
    await ingest_records(db_session, records)
    await ingest_records(db_session, records)
    rows = (await db_session.scalars(select(PriceRow))).all()
    assert len(rows) == 2


async def test_a_republished_correction_wins(db_session: AsyncSession) -> None:
    await ingest_records(db_session, _records([LIVE_ROWS[0]]))
    await ingest_records(db_session, _records([_row(modal_price=2500, max_price=2600)]))
    row = (await db_session.scalars(select(PriceRow))).one()
    assert row.modal_price_qtl == Decimal("2500.00")


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"modal_price": 0, "min_price": 0}, "non_positive_price"),
        ({"min_price": 3000}, "min_above_max"),
        ({"modal_price": 9999}, "modal_outside_range"),
    ],
)
async def test_impossible_rows_are_quarantined_not_dropped(
    db_session: AsyncSession, overrides: dict[str, Any], reason: str
) -> None:
    result = await ingest_records(db_session, _records([_row(**overrides)]))
    assert result.quarantined == 1
    row = (await db_session.scalars(select(PriceRow))).one()
    assert row.status == STATUS_QUARANTINED
    assert row.quarantine_reason == reason  # ops can see WHY


async def test_a_misplaced_decimal_is_quarantined(db_session: AsyncSession) -> None:
    """The defence this check exists for: a price published 10x too high
    must not reach a price card."""
    # Ten ordinary days first, so a median exists to compare against.
    for day in range(1, 11):
        await ingest_records(db_session, _records([_row(arrival_date=f"{day:02d}/08/2026")]))
    result = await ingest_records(
        db_session,
        _records(
            [_row(arrival_date="12/08/2026", min_price=24000, max_price=24100, modal_price=24000)]
        ),
    )
    assert result.quarantined == 1
    row = (
        await db_session.scalars(select(PriceRow).where(PriceRow.arrival_date == date(2026, 8, 12)))
    ).one()
    assert row.quarantine_reason == "outlier_vs_median"


# ── read path ────────────────────────────────────────────────────────


async def test_mandi_block_reflects_ingested_rows(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """AG-A15: the card values are the ingested rows, converted once."""
    rows = [
        _row(
            district="Coimbatore",
            market="Coimbatore market",
            arrival_date="14/08/2026",
            min_price=2300,
            max_price=2350,
            modal_price=2300,
        ),
        _row(
            district="Coimbatore",
            market="Coimbatore market",
            arrival_date="15/08/2026",
            min_price=2380,
            max_price=2410,
            modal_price=2400,
        ),
    ]
    await ingest_records(db_session, _records(rows))

    block = await get_mandi(db_session, "641001")
    assert block is not None
    assert block.source == "Agmarknet"
    assert block.as_of == "2026-08-15"  # newest ingested day, from data
    commodity = block.commodities[0]
    assert commodity.slug == "paddy"
    assert commodity.price == 24.0  # 2400/qtl -> 24.00/kg
    assert commodity.change == 1.0  # 24.00 - 23.00
    assert commodity.series_30d == [23.0, 24.0]  # oldest first
    # The feed publishes no arrivals column, so this is null, not invented.
    assert commodity.arrivals_qtl is None


async def test_one_commodity_never_splices_two_markets(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """A district holds several mandis. Interleaving their prices would
    draw a trend line no single market ever had."""
    rows = [
        # Busy market: two days, the fresher one.
        _row(
            district="Coimbatore",
            market="Coimbatore market",
            arrival_date="14/08/2026",
            min_price=2300,
            max_price=2350,
            modal_price=2300,
        ),
        _row(
            district="Coimbatore",
            market="Coimbatore market",
            arrival_date="15/08/2026",
            min_price=2380,
            max_price=2410,
            modal_price=2400,
        ),
        # A different mandi in the same district, wildly different level.
        _row(
            district="Coimbatore",
            market="Pollachi market",
            arrival_date="13/08/2026",
            min_price=9000,
            max_price=9100,
            modal_price=9000,
        ),
    ]
    await ingest_records(db_session, _records(rows))

    block = await get_mandi(db_session, "641001")
    assert block is not None
    commodity = block.commodities[0]
    assert commodity.market == "Coimbatore market"  # freshest wins
    # Pollachi's 90.0/kg must not appear in Coimbatore's line.
    assert commodity.series_30d == [23.0, 24.0]


async def test_series_is_bounded_to_the_thirty_day_window(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """`series_30d` means 30 days. An old observation must not ride along
    forever just because it was ingested once."""
    rows = [
        _row(
            district="Coimbatore",
            market="Coimbatore market",
            arrival_date="01/06/2026",
            min_price=1000,
            max_price=1100,
            modal_price=1000,
        ),
        _row(
            district="Coimbatore",
            market="Coimbatore market",
            arrival_date="15/08/2026",
            min_price=2380,
            max_price=2410,
            modal_price=2400,
        ),
    ]
    await ingest_records(db_session, _records(rows))

    block = await get_mandi(db_session, "641001")
    assert block is not None
    # The June point is >30 days before the newest day, so it is out.
    assert block.commodities[0].series_30d == [24.0]
    assert block.commodities[0].range_low == 24.0


async def test_quarantined_rows_never_reach_the_site(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await ingest_records(
        db_session,
        _records(
            [
                _row(district="Coimbatore", market="Coimbatore market", min_price=3000)  # min>max
            ]
        ),
    )
    assert (await db_session.scalars(select(PriceRow))).one().status == STATUS_QUARANTINED
    assert await get_mandi(db_session, "641001") is None


async def test_a_pincode_with_no_coverage_gets_the_empty_state(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """Spec §2: 'no market data for this area yet' — never a blank crash
    and never a borrowed price from another district."""
    await ingest_records(db_session, _records(LIVE_ROWS))  # Andhra rows only
    assert await get_mandi(db_session, "641001") is None


async def test_endpoint_serves_the_empty_mandi_block_honestly(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    otp_redis: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no ingested rows the payload still renders: the mandi block
    is present and empty, so the rest of Today survives."""
    from modules.market_data import open_meteo, service

    from .test_market_weather import _forecast

    async def _fake(lat: float, lon: float) -> open_meteo.Forecast:
        return _forecast()

    monkeypatch.setattr(service, "fetch_forecast", _fake)

    client, session = api
    flag = await session.get(FeatureFlag, "agri_today")
    assert flag is not None
    flag.enabled = True
    await session.flush()
    reset_flag_cache()

    body = (await client.get("/market/today/641001")).json()
    assert body["mandi"]["commodities"] == []
    assert body["mandi"]["source"] == "Agmarknet"
    assert body["weather"]["temp_c"] == 25.5  # weather unaffected
