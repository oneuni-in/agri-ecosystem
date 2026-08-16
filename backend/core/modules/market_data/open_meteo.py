"""Open-Meteo forecast client (A-U2 W1).

Deliberately small and hand-rolled, for the same reason billing's
RazorpayClient is (modules/billing/razorpay_client.py): one httpx call
with a timeout and a bounded retry beats a dependency, and the spec bars
new heavy dependencies without justification.

Open-Meteo's free tier needs no API key, so there is no secret here —
only the base URL, which is config (settings.open_meteo_base_url) so
tests point at a double and a self-hosted instance is an env change.

VERIFIED AGAINST THE LIVE API (2026-08-16, Coimbatore centroid):
  - /v1/forecast serves current + daily + hourly in one request.
  - `past_days` returns real observed values, which is how rainfall
    actuals are sourced (no separate archive call).
  - There is NO /v1/warnings endpoint — it 404s. Severe alerts are
    therefore DERIVED from forecast values; see weather.py, which is
    explicit about that in the payload's own source stamp.
  - The API snaps coordinates to its model grid (10.9232,76.9686 came
    back as 10.9315,77.0062), so responses echo the grid cell, not the
    pincode centroid. Nothing downstream may assume they match.

Never logs the query string: this module's CLAUDE.md bars it, and the
query carries a resolved location.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast

import httpx

from settings import get_settings
from shared.telemetry import get_logger

logger = get_logger(__name__)

FORECAST_PATH = "/v1/forecast"

# Requested in one call. Keep this list minimal: every extra variable is
# payload we parse, cache and never render.
CURRENT_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
)
DAILY_FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_gusts_10m_max",
)
HOURLY_FIELDS = ("soil_temperature_6cm",)

# 7 forecast days = the A1 strip width. 7 past days = the rainfall-actual
# window the spec asks for.
FORECAST_DAYS = 7
PAST_DAYS = 7

TIMEZONE = "Asia/Kolkata"


class OpenMeteoError(RuntimeError):
    """Transport failure, timeout, or non-2xx from Open-Meteo."""


@dataclass(frozen=True, slots=True)
class Forecast:
    """The parsed slice of the response the Today payload is built from.

    Lists are parallel to `days` (index 0 = today). `past_precip_mm` runs
    oldest-first over the preceding PAST_DAYS days.
    """

    current: dict[str, Any]
    days: list[str]
    day_code: list[int | None]
    day_high_c: list[float | None]
    day_low_c: list[float | None]
    day_precip_mm: list[float | None]
    day_rain_chance_pct: list[int | None]
    day_gust_kmh: list[float | None]
    soil_temp_c: float | None
    past_precip_mm: list[float]


def _floats(block: dict[str, Any], key: str) -> list[float | None]:
    raw = block.get(key) or []
    return [None if v is None else float(v) for v in raw]


def _ints(block: dict[str, Any], key: str) -> list[int | None]:
    raw = block.get(key) or []
    return [None if v is None else int(v) for v in raw]


def _soil_temp_now(payload: dict[str, Any]) -> float | None:
    """Soil temperature for the current hour.

    The hourly series spans past_days + forecast_days, so the "now" index
    is the first entry on or after the current timestamp rather than a
    fixed offset. Falls back to None (the contract's nullable field)
    rather than picking an arbitrary hour.
    """
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    values = hourly.get("soil_temperature_6cm") or []
    now = str((payload.get("current") or {}).get("time") or "")
    if not (times and values and now):
        return None
    # Hourly stamps are "YYYY-MM-DDTHH:00"; the current stamp carries
    # real minutes, so compare on the hour prefix.
    prefix = now[:13]
    for index, stamp in enumerate(times):
        if str(stamp)[:13] >= prefix and index < len(values):
            value = values[index]
            return None if value is None else float(value)
    return None


async def fetch_forecast(lat: float, lon: float) -> Forecast:
    """One request for current + 7-day forecast + 7-day rainfall actuals.

    Retries once on transport failure (settings.open_meteo_retries): a
    public request path sits behind this, so the budget stays small and
    a miss falls through to the cache's last-known-good instead.
    """
    settings = get_settings()
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "current": ",".join(CURRENT_FIELDS),
        "daily": ",".join(DAILY_FIELDS),
        "hourly": ",".join(HOURLY_FIELDS),
        "timezone": TIMEZONE,
        "forecast_days": str(FORECAST_DAYS),
        "past_days": str(PAST_DAYS),
    }

    attempts = max(1, settings.open_meteo_retries + 1)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(
                base_url=settings.open_meteo_base_url,
                timeout=settings.open_meteo_timeout_seconds,
            ) as client:
                response = await client.get(FORECAST_PATH, params=params)
            if response.status_code >= 400:
                raise OpenMeteoError(f"open-meteo forecast -> {response.status_code}")
            return _parse(cast(dict[str, Any], response.json()))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            last_error = exc
            # Never log the params (they carry a resolved location).
            logger.warning(
                "market.open_meteo_failed",
                extra={"extra_fields": {"attempt": attempt + 1, "exc_type": type(exc).__name__}},
            )
            if attempt + 1 < attempts:
                await asyncio.sleep(0.25 * (attempt + 1))
    raise OpenMeteoError(f"open-meteo forecast failed: {type(last_error).__name__}")


def _parse(payload: dict[str, Any]) -> Forecast:
    daily = payload.get("daily") or {}
    times = [str(t) for t in (daily.get("time") or [])]
    codes = _ints(daily, "weather_code")
    highs = _floats(daily, "temperature_2m_max")
    lows = _floats(daily, "temperature_2m_min")
    precip = _floats(daily, "precipitation_sum")
    chance = _ints(daily, "precipitation_probability_max")
    gusts = _floats(daily, "wind_gusts_10m_max")

    if not times:
        raise OpenMeteoError("open-meteo forecast: empty daily series")

    # past_days rows precede today in the same arrays. Split on the
    # current date rather than a fixed offset: the API trims past rows
    # when history is unavailable for a grid cell.
    today = str((payload.get("current") or {}).get("time") or "")[:10]
    split = times.index(today) if today in times else 0

    def _future[T](values: list[T]) -> list[T]:
        return values[split:]

    past_precip = [v for v in precip[:split] if v is not None]

    return Forecast(
        current=dict(payload.get("current") or {}),
        days=_future(times),
        day_code=_future(codes),
        day_high_c=_future(highs),
        day_low_c=_future(lows),
        day_precip_mm=_future(precip),
        day_rain_chance_pct=_future(chance),
        day_gust_kmh=_future(gusts),
        soil_temp_c=_soil_temp_now(payload),
        past_precip_mm=past_precip,
    )
