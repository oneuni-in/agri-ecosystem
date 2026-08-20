"""A-U1 W3 — the agri.in TODAY payload: THE frozen A-U2 contract.

This shape is mirrored field-for-field in packages/types (TodayPayload —
the frontend renders from that contract). A-U2's real workers (Open-Meteo
D42, Agmarknet D43, schemes E5) must fill THIS shape; the UI must not
change when fixtures are replaced. Change the contract only with a
matching packages/types change and an A-U2 sign-off note.

Editorial text (scheme copy, tips, advisories) is a TranslatedText
{en, ta, hi} — the E5 convention (Vertical.name precedent). Numbers,
codes and stamps are locale-neutral; the UI formats them.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class TranslatedText(BaseModel):
    en: str
    ta: str
    hi: str


class WeatherDay(BaseModel):
    label: TranslatedText
    icon: str  # emoji, v1-official icon set
    high_c: float
    low_c: float


class WeatherAdvisory(BaseModel):
    kind: str  # "spray" at A-U1; open set for A-U2
    title: TranslatedText
    body: TranslatedText


class DailyTip(BaseModel):
    title: TranslatedText
    body: TranslatedText


class WeatherBlock(BaseModel):
    temp_c: float
    condition_icon: str
    condition: TranslatedText
    days: list[WeatherDay]  # 7 entries, today first
    humidity_pct: int
    wind_kmh: int
    wind_dir: str  # compass, e.g. "SW"
    rain_chance_pct: int | None = None
    soil_temp_c: float | None = None
    source: str  # rendered verbatim, e.g. "Open-Meteo · IMD alerts"
    advisory: WeatherAdvisory | None = None
    tip: DailyTip | None = None


class SevereAlert(BaseModel):
    headline: TranslatedText
    district: str
    window: TranslatedText  # "next 48 hrs"
    source: str  # "IMD"
    details_url: str | None = None


class MandiCommodity(BaseModel):
    slug: str
    name: TranslatedText
    emoji: str
    market: str
    unit: str  # "kg" | "pc" | "qtl"
    price: float
    change: float  # signed day-over-day delta; 0 = flat
    series_30d: list[float]  # oldest first; sparkline input
    # ISO arrival dates, one per series_30d point (same order, same length).
    # They exist so a renderer can show the 30-day window's holes — 18–19
    # Aug 2026 is a permanent one (ADR-0012) — instead of drawing
    # evenly-spaced points that interpolate a gap away. Additive on
    # purpose: series_30d keeps its shape and the Today contract stays v2.
    series_days: list[str]
    range_low: float
    range_high: float
    modal: float | None = None
    arrivals_qtl: int | None = None
    note: TranslatedText | None = None  # "MSP ₹24.3", "export demand ↑"


class MandiBlock(BaseModel):
    market: str
    as_of: str  # "6:00 AM" display stamp; NEVER hardcoded in the UI
    source: str  # "Agmarknet"
    commodities: list[MandiCommodity]


class CalendarMonth(BaseModel):
    label: str  # "Aug"
    in_season: bool
    current: bool


class CropWindow(BaseModel):
    icon: str
    label: TranslatedText
    until: TranslatedText | None = None  # "till 25 Aug"


class CalendarBlock(BaseModel):
    zone: TranslatedText  # "TN west zone"
    months: list[CalendarMonth]
    sowing: list[CropWindow]
    harvesting: list[CropWindow]


class SchemeItem(BaseModel):
    level: str  # "central" | "state"
    state_label: TranslatedText | None = None  # chip text for state schemes
    title: TranslatedText
    body: TranslatedText
    verified_against: str  # official domain, e.g. "pmkisan.gov.in"
    verified_on: date
    url: str
    link_label: TranslatedText


class SchemeDeadline(BaseModel):
    chip: str  # "31 AUG" / "72 HRS"
    title: TranslatedText
    note: TranslatedText | None = None


class SchemesBlock(BaseModel):
    items: list[SchemeItem]
    deadlines: list[SchemeDeadline]


class TodayPayload(BaseModel):
    pincode: str = Field(pattern=r"^\d{6}$")
    district: str | None
    generated_at: str  # ISO timestamp
    stub: bool  # pinned False since A-U2: no fixture data is served
    # CONTRACT v2 (A-U2, owner-approved). v1 made this non-nullable, which
    # coupled the two engines: an Open-Meteo outage with a cold cache had
    # to 503 the whole endpoint, taking mandi and the calendar down with
    # it even though both were healthy and living in our own tables.
    # Nullable weather lets them fail independently — the home renders the
    # sections it has and omits the one it does not.
    #
    # `mandi` and `calendar` stay non-nullable ON PURPOSE: both already
    # have honest empty representations (an empty commodity list, an empty
    # month strip) that the UI renders as real empty states, so making
    # them nullable would buy nothing and widen the change.
    weather: WeatherBlock | None
    severe_alert: SevereAlert | None
    mandi: MandiBlock
    calendar: CalendarBlock
    schemes: SchemesBlock


# ── A-U2 W3: commodity pages ─────────────────────────────────────────
# These are NOT part of the frozen Today contract. They back new public
# surfaces (/mandi/*), so they are free to have their own shape.


class CommodityListItem(BaseModel):
    slug: str
    name: TranslatedText
    emoji: str
    unit: str
    market_count: int
    as_of: str  # newest ingested day (ISO), "" when nothing is ingested


class MarketPrice(BaseModel):
    """One market's latest price for a commodity, plus its own series.

    The series is per-MARKET on purpose: splicing markets together would
    draw a trend no mandi ever had (the same rule the home cards follow).
    """

    market_slug: str
    market: str
    district: str
    price: float
    change: float
    series_30d: list[float]
    # ISO arrival dates paired with series_30d (same rule as MandiCommodity:
    # the dates make the window's holes visible to a renderer; additive).
    series_days: list[str]
    range_low: float
    range_high: float
    modal: float | None = None
    as_of: str


class CommodityDetail(BaseModel):
    slug: str
    name: TranslatedText
    emoji: str
    unit: str
    source: str
    as_of: str
    note: TranslatedText | None = None  # MSP overlay, when verified
    markets: list[MarketPrice]


# ── A-U4b C1: ingest-health admin read (admin_router.py) ─────────────
# NOT public contract: an admin-console shape, mirrored nowhere in
# packages/types. One row of market.ingest_runs, verbatim.


class IngestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    started_at: datetime
    finished_at: datetime | None
    outcome: str
    fetched: int
    written: int
    quarantined: int
    newest_arrival_date: date | None
    error: str | None


class IngestRunPage(BaseModel):
    items: list[IngestRunOut]
    next_cursor: str | None = None
