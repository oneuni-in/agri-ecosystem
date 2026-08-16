"""GET /market/today/{pincode}: the flag gate + the frozen contract.

A-U1 wrote these against deterministic fixtures. A-U2 W1 made the
weather half real, so the assertions MOVED rather than went away (spec
§1 W3: "assert shape + stamp presence, not exact prices"):

  - flag OFF is still a 404 and still means the home renders no Today
    section at all — unchanged, this is the A-U1 contract A-U2 inherits;
  - the payload still satisfies every field the UI binds to, now with a
    live forecast driving the weather block;
  - the byte-for-byte determinism assertion became a SHAPE-stability
    assertion: `generated_at` is a real clock now, so identical bytes
    would mean a frozen clock, which is exactly what we removed.

Mandi, calendar and schemes are still A-U1 fixtures here (W2/W3 replace
them); their assertions are untouched so the swap is visible when it
happens.
"""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.market_data import open_meteo, service
from shared.flags import FeatureFlag, reset_flag_cache

from .d26_helpers import api  # noqa: F401 — the shared client fixture
from .test_market_weather import _forecast

pytestmark = pytest.mark.anyio

PINCODE = "641001"


@pytest.fixture
def live_forecast(monkeypatch: pytest.MonkeyPatch) -> None:
    """The captured live Open-Meteo response, in place of the network."""

    async def _fake(lat: float, lon: float) -> open_meteo.Forecast:
        return _forecast()

    monkeypatch.setattr(service, "fetch_forecast", _fake)


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

    # W2/W3 still to land: these three remain A-U1 fixtures, and `stub`
    # stays True until the last one is replaced.
    assert body["stub"] is True
    assert body["mandi"]["source"] and body["mandi"]["as_of"]
    assert len(body["mandi"]["commodities"]) == 8
    for c in body["mandi"]["commodities"]:
        assert len(c["series_30d"]) >= 2  # sparkline needs a line
        assert {"en", "ta", "hi"} <= set(c["name"])
    assert len(body["calendar"]["months"]) == 8
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
