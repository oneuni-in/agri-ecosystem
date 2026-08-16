"""A-U2 W3 — the E5 datasets that replaced the last fixtures.

Schemes, deadline chips, the crop calendar and the MSP overlay are rows
now (migration 0039). What matters here is not that they render, but that
they stay HONEST as time passes and as data is missing:

  - a deadline whose date has passed stops being served;
  - a rolling obligation with no date never expires;
  - a district no zone claims gets no calendar rather than a neighbour's
    sowing dates, which would be actively harmful advice;
  - the MSP overlay is absent until a verified row exists.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.market_data.ingest import ingest_records
from modules.market_data.models import Commodity, Msp, SchemeDeadline
from modules.market_data.service import get_calendar, get_mandi, get_schemes, msp_notes

from .test_market_mandi import _records, _row

pytestmark = pytest.mark.anyio


# ── schemes ──────────────────────────────────────────────────────────


async def test_scheme_cards_carry_their_verification_stamp(db_session: AsyncSession) -> None:
    block = await get_schemes(db_session)
    assert block.items, "0039 seeds the scheme cards"
    for item in block.items:
        assert item.verified_against  # the official domain, rendered
        assert isinstance(item.verified_on, date)
        assert item.url.startswith("https://")
        assert item.title.en and item.title.ta and item.title.hi


async def test_a_passed_deadline_stops_being_served(db_session: AsyncSession) -> None:
    """Advertising a window that closed is worse than showing nothing."""
    chips = {row.chip for row in (await get_schemes(db_session, today=date(2026, 8, 16))).deadlines}
    assert "31 AUG" in chips  # still open on 16 Aug

    later = {row.chip for row in (await get_schemes(db_session, today=date(2026, 9, 20))).deadlines}
    assert "31 AUG" not in later
    assert "15 SEP" not in later


async def test_a_rolling_obligation_never_expires(db_session: AsyncSession) -> None:
    """The PMFBY 72-hour crop-loss intimation applies whenever damage
    happens, so it has no due date and must survive any clock."""
    far_future = await get_schemes(db_session, today=date(2030, 1, 1))
    assert any(row.chip == "72 HRS" for row in far_future.deadlines)

    seeded = (
        await db_session.scalars(select(SchemeDeadline).where(SchemeDeadline.chip == "72 HRS"))
    ).one()
    assert seeded.due_on is None


# ── calendar ─────────────────────────────────────────────────────────


async def test_calendar_strip_is_computed_from_the_clock(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    block = await get_calendar(db_session, "641001", today=date(2026, 8, 16))
    assert block is not None
    assert [month.label for month in block.months] == [
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
        "Jan",
    ]
    current = [month for month in block.months if month.current]
    assert len(current) == 1 and current[0].label == "Aug"
    # Kharif/samba months carry the in-season shading.
    assert {m.label for m in block.months if m.in_season} == {"Jul", "Aug", "Sep", "Oct"}
    assert block.sowing and block.harvesting
    assert block.zone.ta  # zone name is TranslatedText from the row


async def test_the_strip_follows_the_month_over(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """Stored month strips go stale the moment the month turns; this one
    is derived, so it simply moves."""
    block = await get_calendar(db_session, "641001", today=date(2026, 12, 5))
    assert block is not None
    assert [m.label for m in block.months][:3] == ["Oct", "Nov", "Dec"]
    assert next(m for m in block.months if m.current).label == "Dec"


async def test_an_unclaimed_district_gets_no_calendar(db_session: AsyncSession) -> None:
    """A pincode with no zone must not inherit another zone's sowing
    dates — wrong sowing advice is worse than none."""
    assert await get_calendar(db_session, "110001") is None  # not in the geo snapshot


# ── MSP overlay ──────────────────────────────────────────────────────


async def test_no_msp_row_means_no_overlay(db_session: AsyncSession, tn_geo_sample: None) -> None:
    """0039 seeds market.msp EMPTY on purpose: an unverified MSP is worse
    than no MSP, so the note is simply absent."""
    assert await msp_notes(db_session) == {}

    await ingest_records(
        db_session,
        _records([_row(district="Coimbatore", market="Coimbatore market")]),
    )
    block = await get_mandi(db_session, "641001")
    assert block is not None
    assert block.commodities[0].note is None


async def test_a_verified_msp_row_renders_on_the_card(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """AG-A17: the overlay value comes from the verified row, shown in the
    same per-kg unit as the price beside it."""
    paddy = (await db_session.scalars(select(Commodity).where(Commodity.slug == "paddy"))).one()
    db_session.add(
        Msp(
            commodity_id=paddy.id,
            season="Kharif 2026-27",
            price_qtl=Decimal("2430.00"),
            verified_against="cacp.dacnet.nic.in",
            verified_on=date(2026, 8, 16),
        )
    )
    await db_session.flush()

    await ingest_records(
        db_session,
        _records([_row(district="Coimbatore", market="Coimbatore market")]),
    )
    block = await get_mandi(db_session, "641001")
    assert block is not None
    note = block.commodities[0].note
    assert note is not None
    # 2430/qtl -> 24.3/kg, comparable with the ₹24.00/kg price on the card.
    assert note.en == "MSP ₹24.3"
