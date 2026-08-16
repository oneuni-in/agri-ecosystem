"""GET /market/today/{pincode}: the flag gate + the frozen contract.

A-U1 wrote these against deterministic fixtures. A-U2 replaced every
fixture with a real source, so the assertions MOVED rather than went away
(spec §1 W3: "assert shape + stamp presence, not exact prices"):

  - flag OFF is still a 404 and still means the home renders no Today
    section at all — unchanged, this is the A-U1 contract A-U2 inherits;
  - the payload still satisfies every field the UI binds to, now with a
    live forecast driving the weather block;
  - the byte-for-byte determinism assertion became a SHAPE-stability
    assertion: `generated_at` is a real clock now, so identical bytes
    would mean a frozen clock, which is exactly what we removed.

Nothing here is a fixture any more: weather is Open-Meteo, mandi is
ingested Agmarknet rows, and calendar/schemes are the 0039 dataset tables.
`stub` is pinned False, which is the assertion that would fail first if
fixture data ever came back.
"""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.market_data import open_meteo, service
from modules.market_data.agmarknet import parse_record
from modules.market_data.ingest import ingest_records
from shared.flags import FeatureFlag, reset_flag_cache

from .d26_helpers import api  # noqa: F401 — the shared client fixture
from .test_market_mandi import LIVE_ROWS
from .test_market_weather import _forecast

pytestmark = pytest.mark.anyio

PINCODE = "641001"


@pytest.fixture
def live_forecast(monkeypatch: pytest.MonkeyPatch) -> None:
    """The captured live Open-Meteo response, in place of the network."""

    async def _fake(lat: float, lon: float) -> open_meteo.Forecast:
        return _forecast()

    monkeypatch.setattr(service, "fetch_forecast", _fake)


async def _seed_coimbatore_prices(session: AsyncSession) -> None:
    """Two real feed rows, ingested through the real quality gate, so the
    payload's mandi block is genuinely ingested data rather than a mock."""
    rows = [
        _mandi_row(arrival_date="14/08/2026", min_price=2300, max_price=2350, modal_price=2300),
        _mandi_row(arrival_date="15/08/2026", min_price=2380, max_price=2410, modal_price=2400),
    ]
    records = [record for record in (parse_record(row) for row in rows) if record is not None]
    await ingest_records(session, records)
    await session.flush()


def _mandi_row(**overrides: object) -> dict[str, object]:
    row = dict(LIVE_ROWS[0])
    row.update({"district": "Coimbatore", "market": "Coimbatore market"})
    row.update(overrides)
    return row


async def _set_agri_today(session: AsyncSession, enabled: bool) -> None:
    flag = await session.get(FeatureFlag, "agri_today")
    assert flag is not None, "0037 seeds the agri_today flag"
    flag.enabled = enabled
    await session.flush()
    reset_flag_cache()


async def test_flag_off_is_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    await _set_agri_today(session, False)
    r = await client.get(f"/market/today/{PINCODE}")
    assert r.status_code == 404
    assert r.json()["detail"] == "feature_disabled"


async def test_flag_on_serves_the_frozen_contract(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    otp_redis: object,
    live_forecast: None,
) -> None:
    client, session = api
    await _set_agri_today(session, True)
    await _seed_coimbatore_prices(session)
    r = await client.get(f"/market/today/{PINCODE}")
    assert r.status_code == 200
    body = r.json()

    # Contract essentials the UI binds to (mirrored in packages/types).
    assert body["pincode"] == PINCODE
    assert body["district"] == "Coimbatore"  # resolved from geo, not guessed
    assert len(body["weather"]["days"]) == 7
    assert body["weather"]["source"]  # stamp is DATA, never hardcoded in the UI
    assert body["weather"]["advisory"]["kind"] == "spray"
    for block in (body["weather"]["condition"], body["weather"]["advisory"]["title"]):
        assert {"en", "ta", "hi"} <= set(block)  # TranslatedText everywhere

    # MOVED from the fixture's fixed 8 commodities: mandi is ingested
    # data now, so the assertion is about SHAPE and provenance, not a
    # count someone typed. The two rows come from the real feed capture.
    assert body["mandi"]["source"] == "Agmarknet"
    assert body["mandi"]["as_of"] == "2026-08-15"  # newest ingested day
    assert [c["slug"] for c in body["mandi"]["commodities"]] == ["paddy"]
    for c in body["mandi"]["commodities"]:
        assert len(c["series_30d"]) >= 2  # sparkline needs a line
        assert {"en", "ta", "hi"} <= set(c["name"])
        assert c["price"] == 24.0  # 2400/qtl, converted once

    # THE FLIP (W3): every block is real now, so `stub` is pinned False
    # and calendar/schemes come from the 0039 dataset tables.
    assert body["stub"] is False
    assert len(body["calendar"]["months"]) == 8
    assert body["calendar"]["zone"]["ta"], "zone name from the dataset row"
    assert sum(1 for m in body["calendar"]["months"] if m["current"]) == 1
    assert body["schemes"]["items"], "verified scheme entries"
    for item in body["schemes"]["items"]:
        assert item["verified_against"] and item["verified_on"]  # stamp from data
    assert any(d["chip"] == "72 HRS" for d in body["schemes"]["deadlines"])

    # MOVED from "identical bytes": the shape and the cached forecast are
    # stable across calls; only the generated_at clock advances.
    again = await client.get(f"/market/today/{PINCODE}")
    assert again.status_code == 200
    repeat = again.json()
    assert repeat["weather"] == body["weather"]
    assert repeat["mandi"] == body["mandi"]


async def test_calm_weather_has_no_alert(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    otp_redis: object,
    live_forecast: None,
) -> None:
    """The alert strip renders ONLY when an alert is active. An ordinary
    monsoon week is not an alert (see test_market_weather.py for the
    threshold cases)."""
    client, session = api
    await _set_agri_today(session, True)
    r = await client.get("/market/today/600001")  # in the geo sample
    assert r.status_code == 200
    assert r.json()["severe_alert"] is None


async def test_pincode_validation(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    await _set_agri_today(session, True)
    for bad in ("64100", "64100a", "6410011"):
        r = await client.get(f"/market/today/{bad}")
        assert r.status_code == 422, bad
