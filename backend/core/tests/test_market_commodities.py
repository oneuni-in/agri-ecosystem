"""A-U2 W3 — the commodity pages' reads (/market/commodities[/{slug}]).

These back public, indexable pages, so the properties that matter are
about what must NOT be published: a commodity with no prices has no page,
one market's history never absorbs another's, and the window really is 30
days.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.market_data.ingest import ingest_records
from modules.market_data.service import get_commodity, list_commodities

from .d26_helpers import api  # noqa: F401 — the shared client fixture
from .test_market_mandi import _records, _row

pytestmark = pytest.mark.anyio


def _coimbatore(**overrides: Any) -> dict[str, Any]:
    row = _row(district="Coimbatore", market="Coimbatore market")
    row.update(overrides)
    return row


def _pollachi(**overrides: Any) -> dict[str, Any]:
    row = _row(district="Coimbatore", market="Pollachi market")
    row.update(overrides)
    return row


async def test_only_commodities_with_prices_are_listed(db_session: AsyncSession) -> None:
    """The sitemap is built from this list, so a commodity with nothing
    ingested must not appear — advertising an empty page is the failure
    mode here."""
    assert await list_commodities(db_session) == []

    await ingest_records(db_session, _records([_coimbatore()]))
    listed = await list_commodities(db_session)
    assert [item.slug for item in listed] == ["paddy"]
    assert listed[0].market_count == 1
    assert listed[0].as_of == "2026-08-16"
    # Tomato is curated but has no rows, so it is absent — not listed empty.
    assert "tomato" not in {item.slug for item in listed}


async def test_market_count_counts_distinct_markets(db_session: AsyncSession) -> None:
    await ingest_records(
        db_session,
        _records(
            [
                _coimbatore(arrival_date="14/08/2026"),
                _coimbatore(arrival_date="15/08/2026"),
                _pollachi(arrival_date="15/08/2026"),
            ]
        ),
    )
    listed = await list_commodities(db_session)
    assert listed[0].market_count == 2  # three rows, two markets


async def test_detail_keeps_each_market_series_separate(db_session: AsyncSession) -> None:
    """AG-A18: the compare table's rows are per market, and one market's
    line must never absorb another's observations."""
    await ingest_records(
        db_session,
        _records(
            [
                _coimbatore(
                    arrival_date="14/08/2026", min_price=2300, max_price=2350, modal_price=2300
                ),
                _coimbatore(
                    arrival_date="15/08/2026", min_price=2380, max_price=2410, modal_price=2400
                ),
                _pollachi(
                    arrival_date="14/08/2026", min_price=2280, max_price=2320, modal_price=2290
                ),
                _pollachi(
                    arrival_date="15/08/2026", min_price=2340, max_price=2380, modal_price=2360
                ),
            ]
        ),
    )
    detail = await get_commodity(db_session, "paddy")
    assert detail is not None
    assert detail.source == "Agmarknet"
    assert detail.as_of == "2026-08-15"

    by_name = {m.market: m for m in detail.markets}
    assert set(by_name) == {"Coimbatore market", "Pollachi market"}
    assert by_name["Coimbatore market"].series_30d == [23.0, 24.0]
    assert by_name["Pollachi market"].series_30d == [22.9, 23.6]
    # Each point carries its arrival date, so a renderer can show holes.
    assert by_name["Coimbatore market"].series_days == ["2026-08-14", "2026-08-15"]
    assert by_name["Pollachi market"].series_days == ["2026-08-14", "2026-08-15"]
    assert by_name["Coimbatore market"].change == 1.0
    assert by_name["Pollachi market"].change == 0.7
    # Each row carries its OWN as-of: markets report on different days and
    # a stale row must not borrow the page's freshest date.
    assert by_name["Pollachi market"].as_of == "2026-08-15"


async def test_detail_window_is_thirty_days(db_session: AsyncSession) -> None:
    await ingest_records(
        db_session,
        _records(
            [
                _coimbatore(
                    arrival_date="01/06/2026", min_price=1000, max_price=1100, modal_price=1000
                ),
                _coimbatore(
                    arrival_date="15/08/2026", min_price=2380, max_price=2410, modal_price=2400
                ),
            ]
        ),
    )
    detail = await get_commodity(db_session, "paddy")
    assert detail is not None
    assert detail.markets[0].series_30d == [24.0]  # the June point is out
    assert detail.markets[0].series_days == ["2026-08-15"]  # and its date with it


async def test_a_commodity_with_no_prices_has_no_page(db_session: AsyncSession) -> None:
    """None -> the route 404s. A page with no data must not exist rather
    than exist empty."""
    assert await get_commodity(db_session, "tomato") is None  # curated, no rows
    assert await get_commodity(db_session, "not-a-commodity") is None


async def test_quarantined_rows_never_reach_a_commodity_page(db_session: AsyncSession) -> None:
    await ingest_records(db_session, _records([_coimbatore(min_price=3000)]))  # min > max
    assert await get_commodity(db_session, "paddy") is None
    assert await list_commodities(db_session) == []


async def test_endpoints_are_public_and_shaped(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Anonymous reads, no flag: these pages are their own surface and are
    deliberately not gated by agri_today."""
    client, session = api
    await ingest_records(session, _records([_coimbatore()]))
    await session.flush()

    listing = await client.get("/market/commodities")
    assert listing.status_code == 200
    assert [item["slug"] for item in listing.json()] == ["paddy"]

    detail = await client.get("/market/commodities/paddy")
    assert detail.status_code == 200
    body = detail.json()
    assert {"en", "ta", "hi"} <= set(body["name"])
    assert body["markets"][0]["market"] == "Coimbatore market"

    missing = await client.get("/market/commodities/tomato")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "commodity_not_found"

    # Path validation: the slug pattern rejects anything but a slug.
    assert (await client.get("/market/commodities/Not_A_Slug")).status_code == 422
