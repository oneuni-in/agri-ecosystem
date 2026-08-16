"""A-U2 W1 — the real weather worker behind GET /market/today/{pincode}.

Open-Meteo is never called for real here: fetch_forecast is replaced with
a function over a canned response body captured from the LIVE API
(Coimbatore centroid, 2026-08-16), so the parser is tested against the
shape the service actually returns, not one we imagined.

What these lock down:
  - the frozen contract still holds with real data driving it;
  - severe alerts are DERIVED and rare (no alert on an ordinary monsoon
    week, one on an IMD heavy-rain day);
  - the spray window and tip are computed from the numbers;
  - honest degradation: upstream down + warm cache serves stale WITH a
    visible as-of stamp; upstream down + cold cache serves nothing.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.market_data import open_meteo, service
from modules.market_data.open_meteo import OpenMeteoError, _parse
from modules.market_data.weather import (
    build_weather,
    derive_severe_alert,
    now_ist,
    rainfall_7d_mm,
)
from shared.cache import get_redis
from shared.flags import FeatureFlag, reset_flag_cache

from .d26_helpers import api  # noqa: F401 — the shared client fixture

pytestmark = pytest.mark.anyio

PINCODE = "641001"

# Captured from api.open-meteo.com/v1/forecast on 2026-08-16 for the
# Coimbatore centroid, trimmed to the fields the client requests. Three
# past days precede today so the rainfall-actuals split is exercised.
LIVE_SAMPLE: dict[str, Any] = {
    "latitude": 10.931458,
    "longitude": 77.0062,
    "timezone": "Asia/Kolkata",
    "current": {
        "time": "2026-08-16T08:15",
        "temperature_2m": 25.5,
        "relative_humidity_2m": 77,
        "weather_code": 3,
        "wind_speed_10m": 20.9,
        "wind_direction_10m": 222,
    },
    "hourly": {
        "time": ["2026-08-16T07:00", "2026-08-16T08:00", "2026-08-16T09:00"],
        "soil_temperature_6cm": [25.1, 25.9, 26.4],
    },
    "daily": {
        "time": [
            "2026-08-13",
            "2026-08-14",
            "2026-08-15",
            "2026-08-16",
            "2026-08-17",
            "2026-08-18",
            "2026-08-19",
            "2026-08-20",
            "2026-08-21",
            "2026-08-22",
        ],
        "weather_code": [61, 3, 51, 3, 51, 3, 51, 53, 3, 3],
        "temperature_2m_max": [30.1, 31.0, 30.6, 32.3, 31.8, 31.8, 31.6, 31.7, 31.9, 31.5],
        "temperature_2m_min": [22.0, 22.2, 22.1, 22.3, 22.6, 22.4, 22.1, 22.4, 21.8, 21.6],
        "precipitation_sum": [4.2, 0.0, 1.1, 0.0, 0.2, 0.0, 0.7, 2.7, 0.0, 0.0],
        "precipitation_probability_max": [70, 20, 45, 57, 57, 80, 100, 98, 39, 31],
        "wind_gusts_10m_max": [60.0, 58.0, 61.0, 65.2, 61.6, 55.1, 55.4, 55.1, 63.4, 58.3],
    },
}


def _sample(**daily_overrides: list[Any]) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(json.dumps(LIVE_SAMPLE))
    body["daily"].update(daily_overrides)
    return body


def _forecast(**daily_overrides: list[Any]) -> open_meteo.Forecast:
    return _parse(_sample(**daily_overrides))


async def _enable(session: AsyncSession) -> None:
    flag = await session.get(FeatureFlag, "agri_today")
    assert flag is not None, "0037 seeds the agri_today flag"
    flag.enabled = True
    await session.flush()
    reset_flag_cache()


# ── parser ───────────────────────────────────────────────────────────


def test_parse_splits_past_from_forecast() -> None:
    forecast = _forecast()
    # Today is 2026-08-16: 3 past days, 7 forecast days.
    assert forecast.days[0] == "2026-08-16"
    assert len(forecast.days) == 7
    assert forecast.past_precip_mm == [4.2, 0.0, 1.1]
    assert rainfall_7d_mm(forecast) == 5.3


def test_parse_picks_soil_temp_for_the_current_hour() -> None:
    # current time is 08:15 -> the 08:00 row, not the first row.
    assert _forecast().soil_temp_c == 25.9


def test_parse_rejects_an_empty_series() -> None:
    body = _sample()
    body["daily"]["time"] = []
    with pytest.raises(OpenMeteoError):
        _parse(body)


# ── weather block ────────────────────────────────────────────────────


def test_weather_block_carries_real_values() -> None:
    block = build_weather(_forecast())
    assert block.temp_c == 25.5
    assert block.humidity_pct == 77
    assert block.wind_kmh == 21
    assert block.wind_dir == "SW"  # 222° -> SW
    assert block.soil_temp_c == 25.9
    assert block.source == "Open-Meteo"
    assert len(block.days) == 7
    assert block.days[0].label.en == "Today"
    assert block.days[1].label.en == "Mon"  # 2026-08-17 is a Monday
    for day in block.days:
        assert {day.label.en, day.label.ta, day.label.hi} != {""}


def test_spray_advisory_names_the_window() -> None:
    # Today is dry (code 3, 57% chance is under the 40%? no — 57 >= 40),
    # so the advisory should say when it reopens rather than claim a window.
    block = build_weather(_forecast())
    assert block.advisory is not None
    assert block.advisory.kind == "spray"
    for locale in (block.advisory.body.en, block.advisory.body.ta, block.advisory.body.hi):
        assert locale.strip()


def test_spray_advisory_opens_on_a_dry_forecast() -> None:
    dry = _forecast(
        weather_code=[61, 3, 51, 0, 0, 0, 1, 53, 3, 3],
        precipitation_sum=[4.2, 0.0, 1.1, 0.0, 0.0, 0.0, 0.0, 2.7, 0.0, 0.0],
        precipitation_probability_max=[70, 20, 45, 5, 10, 8, 12, 98, 39, 31],
    )
    block = build_weather(dry)
    assert block.advisory is not None
    body = block.advisory.body.en
    assert "Good spraying conditions till" in body
    # The run breaks at 2026-08-20 (98% chance) -> names the day after.
    assert "Avoid from" in body


def test_tip_fires_on_runoff_risk_and_is_omitted_otherwise() -> None:
    runoff = _forecast(precipitation_sum=[4.2, 0.0, 1.1, 0.0, 35.0, 0.0, 0.7, 2.7, 0.0, 0.0])
    tip = build_weather(runoff).tip
    assert tip is not None
    assert "urea" in tip.body.en

    # Nothing notable: no heavy rain, not a 5-day dry spell, humidity
    # under the fungal threshold -> no tip at all rather than filler.
    quiet = _forecast(
        weather_code=[61, 3, 51, 3, 3, 3, 3, 3, 3, 3],
        precipitation_sum=[4.2, 0.0, 1.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        precipitation_probability_max=[70, 20, 45, 30, 30, 30, 30, 30, 30, 30],
    )
    assert build_weather(quiet).tip is None


# ── severe alerts ────────────────────────────────────────────────────


def test_no_alert_on_an_ordinary_monsoon_week() -> None:
    """The measured Coimbatore week gusts at 65 km/h and rains a few mm.
    A strip that fires on that teaches people to ignore it."""
    assert derive_severe_alert(_forecast(), "Coimbatore") is None


def test_heavy_rain_crosses_the_imd_threshold() -> None:
    alert = derive_severe_alert(
        _forecast(precipitation_sum=[4.2, 0.0, 1.1, 0.0, 80.0, 0.0, 0.7, 2.7, 0.0, 0.0]),
        "Coimbatore",
    )
    assert alert is not None
    assert alert.headline.en == "Heavy rain warning"
    assert alert.district == "Coimbatore"
    assert alert.window.en == "next 48 hrs"  # day index 1
    # Honest labelling: this is our derivation over Open-Meteo numbers,
    # never claimed as an IMD bulletin.
    assert alert.source == "open-meteo"
    assert "IMD" not in alert.source


def test_the_most_severe_condition_wins() -> None:
    alert = derive_severe_alert(
        _forecast(precipitation_sum=[4.2, 0.0, 1.1, 70.0, 210.0, 0.0, 0.7, 2.7, 0.0, 0.0]),
        "Coimbatore",
    )
    assert alert is not None
    assert alert.headline.en == "Extremely heavy rain warning"


def test_alert_needs_a_district_to_name() -> None:
    heavy = _forecast(precipitation_sum=[4.2, 0.0, 1.1, 80.0, 0.0, 0.0, 0.7, 2.7, 0.0, 0.0])
    assert derive_severe_alert(heavy, None) is None


# ── endpoint + degradation ───────────────────────────────────────────


async def test_endpoint_serves_real_weather(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    otp_redis: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session = api
    await _enable(session)

    async def _fake(lat: float, lon: float) -> open_meteo.Forecast:
        # The centroid really is resolved from geo, not hardcoded.
        assert round(lat, 2) == 10.92
        return _forecast()

    monkeypatch.setattr(service, "fetch_forecast", _fake)

    response = await client.get(f"/market/today/{PINCODE}")
    assert response.status_code == 200
    body = response.json()

    assert body["district"] == "Coimbatore"  # real geo, not the fixture guess
    assert body["weather"]["source"] == "Open-Meteo"
    assert body["weather"]["temp_c"] == 25.5
    assert len(body["weather"]["days"]) == 7
    assert body["severe_alert"] is None  # ordinary week
    for day in body["weather"]["days"]:
        assert {"en", "ta", "hi"} <= set(day["label"])


async def test_outage_with_a_warm_cache_serves_stale_with_a_visible_stamp(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    otp_redis: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AG-A19: kill the upstream, reload, and the page still renders —
    with the age of the data on its face."""
    client, session = api
    await _enable(session)

    # Prime last-known-good as if taken yesterday.
    stale_at = now_ist() - timedelta(hours=20)
    await service._cache_put(PINCODE, _forecast(), stale_at)
    # Expire only the fresh window, keeping last-known-good.
    await get_redis().delete(service.FRESH_KEY.format(pincode=PINCODE))

    async def _down(lat: float, lon: float) -> open_meteo.Forecast:
        raise OpenMeteoError("simulated outage")

    monkeypatch.setattr(service, "fetch_forecast", _down)

    response = await client.get(f"/market/today/{PINCODE}")
    assert response.status_code == 200
    source = response.json()["weather"]["source"]
    assert source.startswith("Open-Meteo · as of ")
    assert "AM" in source or "PM" in source


async def test_outage_with_a_cold_cache_shows_nothing_rather_than_lying(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    otp_redis: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session = api
    await _enable(session)

    async def _down(lat: float, lon: float) -> open_meteo.Forecast:
        raise OpenMeteoError("simulated outage")

    monkeypatch.setattr(service, "fetch_forecast", _down)

    response = await client.get(f"/market/today/{PINCODE}")
    assert response.status_code == 503
    assert response.json()["detail"] == "weather_unavailable"


async def test_pincode_outside_the_loaded_geography_has_no_weather(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    otp_redis: object,
) -> None:
    client, session = api
    await _enable(session)
    # 110001 (Delhi) is not in the TN-only geo snapshot.
    response = await client.get("/market/today/110001")
    assert response.status_code == 503


async def test_flag_off_is_still_a_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    flag = await session.get(FeatureFlag, "agri_today")
    assert flag is not None
    flag.enabled = False
    await session.flush()
    reset_flag_cache()
    response = await client.get(f"/market/today/{PINCODE}")
    assert response.status_code == 404
    assert response.json()["detail"] == "feature_disabled"
