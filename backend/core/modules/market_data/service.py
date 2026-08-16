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
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from settings import get_settings
from shared.cache import get_redis
from shared.geo.service import centroid_for_pincode, district_for_pincode
from shared.telemetry import get_logger

from .models import (
    STATUS_ACTIVE,
    Commodity,
    CropCalendar,
    Market,
    Msp,
    PriceRow,
    Scheme,
    SchemeDeadline,
    per_kg,
)
from .open_meteo import Forecast, OpenMeteoError, fetch_forecast
from .schemas import (
    CalendarBlock,
    CalendarMonth,
    CropWindow,
    MandiBlock,
    MandiCommodity,
    SchemeItem,
    SchemesBlock,
    SevereAlert,
    TranslatedText,
    WeatherBlock,
)
from .schemas import SchemeDeadline as SchemeDeadline_
from .weather import SOURCE, build_weather, day_stamp, derive_severe_alert, now_ist

logger = get_logger(__name__)

# The contract field is series_30d; this is that window.
SERIES_WINDOW_DAYS = 30

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


# ── mandi (W2) ───────────────────────────────────────────────────────


async def get_mandi(session: AsyncSession, pincode: str) -> MandiBlock | None:
    """Latest curated prices for the visitor's district, or None.

    None means "no market data for this area yet" — the spec's third
    degradation case. It is returned whenever the district has no
    ingested rows, which is the honest state for most of India until the
    ingest widens beyond the launch state.

    Only `status='active'` rows are read: a quarantined row is visible to
    ops and to nobody else.
    """
    district = await district_for_pincode(session, pincode)
    if district is None:
        return None

    # The window the contract's `series_30d` names. Anchored on the
    # newest ingested day, not on today: on a Sunday (or any day the
    # feed is quiet) "today" would slide the window off real data.
    newest_day = await session.scalar(
        select(func.max(PriceRow.arrival_date))
        .join(Market, Market.id == PriceRow.market_id)
        .where(Market.district == district.name, PriceRow.status == STATUS_ACTIVE)
    )
    if newest_day is None:
        return None
    window_start = newest_day - timedelta(days=SERIES_WINDOW_DAYS)

    rows = (
        await session.execute(
            select(PriceRow, Commodity, Market)
            .join(Commodity, Commodity.id == PriceRow.commodity_id)
            .join(Market, Market.id == PriceRow.market_id)
            .where(
                Market.district == district.name,
                PriceRow.status == STATUS_ACTIVE,
                PriceRow.arrival_date > window_start,
            )
            # variety/grade break ties so one date yields one point
            # deterministically instead of whichever row the planner
            # happened to return first.
            .order_by(
                Commodity.slug,
                PriceRow.arrival_date.desc(),
                PriceRow.variety,
                PriceRow.grade,
            )
        )
    ).all()
    if not rows:
        return None

    # Group by commodity AND market: a district can hold several mandis,
    # and splicing their prices into one line would draw a trend that no
    # single market ever had.
    by_pair: dict[tuple[str, uuid.UUID], list[tuple[PriceRow, Commodity, Market]]] = {}
    for price, commodity, market in rows:
        by_pair.setdefault((commodity.slug, market.id), []).append((price, commodity, market))

    # One market per commodity: the one with the freshest observation,
    # breaking ties on the longer history.
    best: dict[str, list[tuple[PriceRow, Commodity, Market]]] = {}
    for (slug, _market_id), entries in by_pair.items():
        incumbent = best.get(slug)
        if incumbent is None or (entries[0][0].arrival_date, len(entries)) > (
            incumbent[0][0].arrival_date,
            len(incumbent),
        ):
            best[slug] = entries

    # MSP overlay, where a verified row exists for the commodity.
    notes = await msp_notes(session)

    commodities: list[MandiCommodity] = []
    latest_date: date | None = None
    market_name = ""

    for entries in best.values():
        # One point per date (the first row after the deterministic sort).
        per_day: dict[date, PriceRow] = {}
        for price, _c, _m in entries:
            per_day.setdefault(price.arrival_date, price)
        days = sorted(per_day)

        newest, commodity, market = entries[0]
        if latest_date is None or newest.arrival_date > latest_date:
            latest_date = newest.arrival_date
            market_name = market.name

        # Oldest first — the sparkline input. Only real observations:
        # a series with one point renders no line, which is correct on
        # day one of ingestion rather than a fabricated trend.
        series = [per_kg(per_day[day].modal_price_qtl) for day in days]
        prices = series

        previous = per_day[days[-2]] if len(days) > 1 else None
        change = (
            round(per_kg(newest.modal_price_qtl) - per_kg(previous.modal_price_qtl), 2)
            if previous is not None
            else 0.0
        )

        commodities.append(
            MandiCommodity(
                slug=commodity.slug,
                name=TranslatedText(**commodity.name),
                emoji=commodity.emoji,
                market=market.name,
                unit=commodity.display_unit,
                price=per_kg(newest.modal_price_qtl),
                change=change,
                series_30d=series,
                range_low=min(prices),
                range_high=max(prices),
                modal=per_kg(newest.modal_price_qtl),
                # Agmarknet's daily-price resource publishes no arrivals
                # figure, so this stays null rather than invented.
                arrivals_qtl=None,
                note=notes.get(commodity.id),
            )
        )

    commodities.sort(key=lambda item: item.slug)
    return MandiBlock(
        market=market_name,
        as_of=latest_date.isoformat() if latest_date else "",
        source="Agmarknet",
        commodities=commodities,
    )


# ── schemes + calendar + MSP (W3) ────────────────────────────────────

# The A1 strip shows eight months starting two before the current one, so
# "now" sits in context rather than at the left edge.
_STRIP_MONTHS = 8
_STRIP_LOOKBACK = 2
_MONTH_LABELS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


async def get_schemes(session: AsyncSession, today: date | None = None) -> SchemesBlock:
    """Scheme cards + the deadline chips still worth showing.

    A deadline whose `due_on` has passed is dropped rather than served:
    advertising a window that closed is worse than showing nothing.
    Rolling obligations (due_on NULL) always survive.
    """
    now = today or now_ist().date()

    schemes = (await session.scalars(select(Scheme).order_by(Scheme.sort_order, Scheme.id))).all()
    deadlines = (
        await session.scalars(
            select(SchemeDeadline)
            .where(
                or_(SchemeDeadline.due_on.is_(None), SchemeDeadline.due_on >= now),
            )
            .order_by(SchemeDeadline.sort_order, SchemeDeadline.id)
        )
    ).all()

    return SchemesBlock(
        items=[
            SchemeItem(
                level=row.level,
                state_label=TranslatedText(**row.state_label) if row.state_label else None,
                title=TranslatedText(**row.title),
                body=TranslatedText(**row.body),
                verified_against=row.verified_against,
                verified_on=row.verified_on,
                url=row.url,
                link_label=TranslatedText(**row.link_label),
            )
            for row in schemes
        ],
        deadlines=[
            SchemeDeadline_(
                chip=row.chip,
                title=TranslatedText(**row.title),
                note=TranslatedText(**row.note) if row.note else None,
            )
            for row in deadlines
        ],
    )


def _crop_windows(entries: list[dict[str, Any]]) -> list[CropWindow]:
    return [
        CropWindow(
            icon=str(entry.get("icon") or ""),
            label=TranslatedText(**entry["label"]),
            until=TranslatedText(**entry["until"]) if entry.get("until") else None,
        )
        for entry in entries
    ]


async def get_calendar(
    session: AsyncSession, pincode: str, today: date | None = None
) -> CalendarBlock | None:
    """The crop calendar for the zone covering this pincode's district.

    None when no zone claims the district — an honest "we have not written
    a calendar for your area" rather than another zone's sowing dates,
    which would be actively harmful advice.
    """
    district = await district_for_pincode(session, pincode)
    if district is None:
        return None

    zones = (await session.scalars(select(CropCalendar))).all()
    zone = next((row for row in zones if district.name in (row.districts or [])), None)
    if zone is None:
        return None

    now = today or now_ist().date()
    in_season = set(zone.in_season_months or [])
    months: list[CalendarMonth] = []
    for offset in range(_STRIP_MONTHS):
        index = (now.month - 1 - _STRIP_LOOKBACK + offset) % 12
        months.append(
            CalendarMonth(
                label=_MONTH_LABELS[index],
                in_season=(index + 1) in in_season,
                current=(index + 1) == now.month,
            )
        )

    return CalendarBlock(
        zone=TranslatedText(**zone.name),
        months=months,
        sowing=_crop_windows(zone.sowing or []),
        harvesting=_crop_windows(zone.harvesting or []),
    )


async def msp_notes(session: AsyncSession) -> dict[uuid.UUID, TranslatedText]:
    """commodity_id -> the MSP note rendered on its price card.

    Empty while market.msp is empty (0039 seeds no rows on purpose), so
    the overlay simply does not appear until a human has verified the
    numbers against CACP/PIB.
    """
    rows = (await session.scalars(select(Msp))).all()
    notes: dict[uuid.UUID, TranslatedText] = {}
    for row in rows:
        # Shown in the same per-kg unit as the price beside it, so the two
        # numbers are directly comparable.
        rupees = per_kg(row.price_qtl)
        notes[row.commodity_id] = TranslatedText(
            en=f"MSP ₹{rupees}",
            ta=f"MSP ₹{rupees}",
            hi=f"MSP ₹{rupees}",
        )
    return notes
