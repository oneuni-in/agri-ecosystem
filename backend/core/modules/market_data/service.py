"""Market Data module public service interface (A-U2).

W1 lands the weather half: resolve a pincode to a centroid, fetch
Open-Meteo through a Redis cache, and build the frozen contract's
WeatherBlock / SevereAlert from it.

CACHE AND HONEST DEGRADATION (spec §2)
Two keys per pincode:
  market:wx:{pincode}       — fresh window (weather_cache_ttl_seconds)
  market:wx:last:{pincode}  — last known good (weather_stale_ttl_seconds)
A fresh hit serves as-is. A miss fetches; if the fetch fails we fall
back to last-known-good and stamp the source with the time it was
actually taken ("Open-Meteo · as of 15 Aug 6:00 AM"), so a farmer
reading a stale forecast can see that it is stale. With neither, weather
is unavailable and we say so by returning None — never a placeholder
number.

Redis being down is not an outage of this module: every cache call is
best-effort, and a failure just means we go to the API every time.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from settings import get_settings
from shared.cache import get_redis
from shared.geo.service import centroid_for_pincode, district_for_pincode
from shared.telemetry import get_logger

from .open_meteo import Forecast, OpenMeteoError, fetch_forecast
from .schemas import SevereAlert, WeatherBlock
from .weather import SOURCE, build_weather, day_stamp, derive_severe_alert, now_ist

logger = get_logger(__name__)

FRESH_KEY = "market:wx:{pincode}"
STALE_KEY = "market:wx:last:{pincode}"


def _encode(forecast: Forecast, fetched_at: datetime) -> str:
    return json.dumps({"fetched_at": fetched_at.isoformat(), "forecast": asdict(forecast)})


def _decode(raw: str) -> tuple[Forecast, datetime]:
    data: dict[str, Any] = json.loads(raw)
    return Forecast(**data["forecast"]), datetime.fromisoformat(data["fetched_at"])


async def _cache_get(key: str) -> tuple[Forecast, datetime] | None:
    try:
        raw = await get_redis().get(key)
    except Exception as exc:  # a redis blip must not fail the page
        logger.warning(
            "market.cache_read_failed", extra={"extra_fields": {"exc_type": type(exc).__name__}}
        )
        return None
    if not raw:
        return None
    try:
        # decode_responses=True on the shared client, so this is str;
        # redis-py's stubs still type the reply as the loose bytes|str
        # union (same cast idiom as shared/events.py).
        return _decode(cast(str, raw))
    except (ValueError, KeyError, TypeError):
        # A cache entry written by an older shape is not an error worth
        # surfacing — treat it as a miss and let the next fetch replace it.
        return None


async def _cache_put(pincode: str, forecast: Forecast, fetched_at: datetime) -> None:
    settings = get_settings()
    payload = _encode(forecast, fetched_at)
    try:
        redis = get_redis()
        await redis.set(
            FRESH_KEY.format(pincode=pincode), payload, ex=settings.weather_cache_ttl_seconds
        )
        await redis.set(
            STALE_KEY.format(pincode=pincode), payload, ex=settings.weather_stale_ttl_seconds
        )
    except Exception as exc:
        logger.warning(
            "market.cache_write_failed", extra={"extra_fields": {"exc_type": type(exc).__name__}}
        )


async def _forecast_for(pincode: str, lat: float, lon: float) -> tuple[Forecast, datetime] | None:
    """Fresh cache -> live fetch -> last known good. None if all three miss."""
    fresh = await _cache_get(FRESH_KEY.format(pincode=pincode))
    if fresh is not None:
        return fresh

    try:
        forecast = await fetch_forecast(lat, lon)
    except OpenMeteoError:
        stale = await _cache_get(STALE_KEY.format(pincode=pincode))
        if stale is not None:
            logger.info("market.weather_served_stale", extra={"extra_fields": {"pincode": pincode}})
        else:
            logger.warning(
                "market.weather_unavailable", extra={"extra_fields": {"pincode": pincode}}
            )
        return stale

    fetched_at = now_ist()
    await _cache_put(pincode, forecast, fetched_at)
    return forecast, fetched_at


async def get_weather(
    session: AsyncSession, pincode: str
) -> tuple[WeatherBlock, SevereAlert | None] | None:
    """Weather + any derived alert for a pincode.

    None means "no weather to show": either the pincode has no centroid
    in geo (outside the loaded geography) or the upstream is down with
    nothing cached. Both are empty states, never invented numbers.
    """
    centroid = await centroid_for_pincode(session, pincode)
    if centroid is None:
        logger.info("market.no_centroid", extra={"extra_fields": {"pincode": pincode}})
        return None
    lat, lon = centroid

    result = await _forecast_for(pincode, float(lat), float(lon))
    if result is None:
        return None
    forecast, fetched_at = result

    # Stale reads carry their real age in the rendered source string.
    age = (now_ist() - fetched_at).total_seconds()
    source = SOURCE
    if age > get_settings().weather_cache_ttl_seconds:
        source = f"{SOURCE} · as of {day_stamp(fetched_at)}"

    district = await district_for_pincode(session, pincode)
    district_name = district.name if district is not None else None

    return build_weather(forecast, source=source), derive_severe_alert(forecast, district_name)


async def district_name_for(session: AsyncSession, pincode: str) -> str | None:
    district = await district_for_pincode(session, pincode)
    return district.name if district is not None else None
