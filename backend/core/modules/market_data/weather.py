"""Forecast -> WeatherBlock / SevereAlert (A-U2 W1).

Everything here is a pure function of a real Open-Meteo response. No
value is invented: numbers pass through, words come from the WMO lexicon
(wmo.py), and the two pieces of GUIDANCE — the spray window and the tip
— are computed from the forecast under thresholds stated in this file,
never written by a human pretending to advise a specific farm.

SEVERE ALERTS, AND WHY THEY SAY "DERIVED":
Open-Meteo publishes no warnings endpoint (verified 2026-08-16:
/v1/warnings 404s), so there is no official warning to relay. Rather
than drop the strip or — far worse — label our own arithmetic "IMD",
alerts are DERIVED here: IMD's *published* rainfall categories applied
to Open-Meteo's forecast numbers. The classification scale is IMD's
public one; the measurements are Open-Meteo's; the payload's source
field says open-meteo, because that is whose data it is. If a real IMD
warning feed is licensed later, this function is the only thing that
changes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from .open_meteo import Forecast
from .schemas import (
    DailyTip,
    SevereAlert,
    TranslatedText,
    WeatherAdvisory,
    WeatherBlock,
    WeatherDay,
)
from .wmo import TODAY_LABEL, WEEKDAYS, compass, describe, is_wet

# India Standard Time as a FIXED offset, deliberately not
# ZoneInfo("Asia/Kolkata"): IST is UTC+5:30 year-round with no DST in
# its entire history, and zoneinfo needs the IANA database, which
# Windows does not ship — a dev box without the `tzdata` package raises
# ZoneInfoNotFoundError while CI's Linux passes. A fixed offset is exact
# here and identical on both.
IST = timezone(timedelta(hours=5, minutes=30))

SOURCE = "Open-Meteo"
ALERT_SOURCE = "open-meteo"

# --- spray window ----------------------------------------------------
# A day is sprayable when rain is unlikely enough that the application
# will not be washed off: agrochemical labels generally want a rain-free
# window of several hours after application.
SPRAY_MAX_RAIN_CHANCE_PCT = 40
SPRAY_MAX_PRECIP_MM = 1.0

# --- severe alert thresholds -----------------------------------------
# IMD's published 24-hour rainfall classification (mm/day).
HEAVY_RAIN_MM = 64.5
VERY_HEAVY_RAIN_MM = 115.6
EXTREMELY_HEAVY_RAIN_MM = 204.5
# Gale-force gusts. Set well above the 60-65 km/h gusts that are routine
# in a Tamil Nadu monsoon (measured, Coimbatore, Aug 2026) — an alert
# that fires most days is noise, and noise is how people learn to ignore
# a warning strip.
GALE_GUST_KMH = 80.0
# How far ahead an alert is worth interrupting the page for.
ALERT_HORIZON_DAYS = 3

# --- tip rules -------------------------------------------------------
# Rain heavy enough to carry surface-applied nitrogen away as runoff.
TIP_RUNOFF_MM = 20.0
TIP_DRY_SPELL_DAYS = 5
TIP_DRY_MAX_CHANCE_PCT = 20
TIP_HUMID_PCT = 85


def _t(en: str, ta: str, hi: str) -> TranslatedText:
    return TranslatedText(en=en, ta=ta, hi=hi)


def _weekday_label(iso_day: str, index: int) -> TranslatedText:
    if index == 0:
        return TODAY_LABEL
    return WEEKDAYS[date.fromisoformat(iso_day).weekday()]


def _days(forecast: Forecast) -> list[WeatherDay]:
    out: list[WeatherDay] = []
    for index, iso_day in enumerate(forecast.days[:7]):
        icon, _label = describe(forecast.day_code[index])
        high = forecast.day_high_c[index]
        low = forecast.day_low_c[index]
        # A day with no temperature is not a day we can draw; skipping
        # keeps the strip honest (it renders what exists) instead of
        # showing a 0°C column.
        if high is None or low is None:
            continue
        out.append(
            WeatherDay(
                label=_weekday_label(iso_day, index),
                icon=icon,
                high_c=round(high, 1),
                low_c=round(low, 1),
            )
        )
    return out


def _sprayable(forecast: Forecast, index: int) -> bool:
    chance = forecast.day_rain_chance_pct[index]
    precip = forecast.day_precip_mm[index]
    if is_wet(forecast.day_code[index]):
        return False
    if chance is not None and chance >= SPRAY_MAX_RAIN_CHANCE_PCT:
        return False
    return not (precip is not None and precip >= SPRAY_MAX_PRECIP_MM)


def _spray_advisory(forecast: Forecast) -> WeatherAdvisory | None:
    """Computed spray guidance, or None when the forecast says nothing
    useful. Never claims a window it cannot see: the horizon is however
    many days the API returned."""
    horizon = len(forecast.days)
    if horizon == 0:
        return None

    title = _t("Spray window advisory", "தெளிப்பு நேர அறிவுரை", "छिड़काव सलाह")

    if not _sprayable(forecast, 0):
        # Closed today — say when it reopens, if it does inside the
        # forecast.
        reopen = next((i for i in range(1, horizon) if _sprayable(forecast, i)), None)
        if reopen is None:
            body = _t(
                "Rain likely across the whole forecast — hold off spraying; "
                "application now is likely to wash off.",
                "முழு வானிலை முன்னறிவிப்பிலும் மழை — இப்போது தெளிக்க வேண்டாம், மருந்து அடித்துச் செல்லப்படும்.",
                "पूरे पूर्वानुमान में बारिश — अभी छिड़काव न करें, दवा बह जाएगी।",
            )
        else:
            day = _weekday_label(forecast.days[reopen], reopen)
            body = _t(
                f"Rain likely today — postpone spraying. Conditions look "
                f"suitable again from {day.en}.",
                f"இன்று மழை வாய்ப்பு — தெளிப்பதை தள்ளிப்போடுங்கள். {day.ta} முதல் மீண்டும் ஏற்றது.",
                f"आज बारिश संभव — छिड़काव टालें। {day.hi} से दोबारा उपयुक्त।",
            )
        return WeatherAdvisory(kind="spray", title=title, body=body)

    # Open today — find where the run ends.
    last_open = 0
    for index in range(1, horizon):
        if not _sprayable(forecast, index):
            break
        last_open = index

    if last_open == horizon - 1:
        body = _t(
            "Good spraying conditions across the forecast — no wash-off rain expected.",
            "முன்னறிவிப்பு முழுவதும் தெளிக்க ஏற்ற நிலை — மருந்து அடித்துச் செல்லும் மழை இல்லை.",
            "पूरे पूर्वानुमान में छिड़काव अनुकूल — बहा देने वाली बारिश नहीं।",
        )
    else:
        end = _weekday_label(forecast.days[last_open], last_open)
        wet = _weekday_label(forecast.days[last_open + 1], last_open + 1)
        body = _t(
            f"Good spraying conditions till {end.en}. Avoid from {wet.en} — "
            f"rain likely to wash off application.",
            f"{end.ta} வரை தெளிக்கலாம். {wet.ta} முதல் தவிர்க்கவும் — மழை மருந்தை அடித்துச் செல்லும்.",
            f"{end.hi} तक छिड़काव ठीक। {wet.hi} से बचें — बारिश दवा बहा देगी।",
        )
    return WeatherAdvisory(kind="spray", title=title, body=body)


def _tip(forecast: Forecast, humidity_pct: int) -> DailyTip | None:
    """One computed agronomic note, or None.

    Each branch is a consequence of numbers actually in the forecast. If
    none applies, the tip is omitted — the UI renders only what exists,
    and a filler tip would be invented content.
    """
    title = _t("Tip of the day", "இன்றைய குறிப்பு", "आज का सुझाव")
    horizon = min(len(forecast.days), 3)

    runoff = next(
        (
            index
            for index in range(horizon)
            if (forecast.day_precip_mm[index] or 0.0) >= TIP_RUNOFF_MM
        ),
        None,
    )
    if runoff is not None:
        day = _weekday_label(forecast.days[runoff], runoff)
        return DailyTip(
            title=title,
            body=_t(
                f"Heavy rain expected {day.en} — postpone urea top-dressing. "
                f"Nitrogen applied before heavy rain is lost to runoff.",
                f"{day.ta} கனமழை — யூரியா இடுவதை தள்ளிப்போடுங்கள். கனமழைக்கு முன் இட்டால் நைட்ரஜன் வீணாகும்.",
                f"{day.hi} भारी बारिश — यूरिया टॉप-ड्रेसिंग टालें। "
                f"भारी बारिश से पहले डाला नाइट्रोजन बह जाता है।",
            ),
        )

    dry_window = forecast.day_rain_chance_pct[:TIP_DRY_SPELL_DAYS]
    if len(dry_window) == TIP_DRY_SPELL_DAYS and all(
        (chance or 0) < TIP_DRY_MAX_CHANCE_PCT for chance in dry_window
    ):
        return DailyTip(
            title=title,
            body=_t(
                "No rain in the next five days — plan irrigation and mulch to hold soil moisture.",
                "அடுத்த ஐந்து நாட்களில் மழை இல்லை — பாசனம் திட்டமிடுங்கள், மண் ஈரப்பதம் காக்க மூடாக்கு இடுங்கள்.",
                "अगले पांच दिन बारिश नहीं — सिंचाई की योजना बनाएं और नमी बचाने को मल्च करें।",
            ),
        )

    if humidity_pct >= TIP_HUMID_PCT and any(is_wet(code) for code in forecast.day_code[:horizon]):
        return DailyTip(
            title=title,
            body=_t(
                "High humidity with wet spells — scout for fungal leaf spot and "
                "keep field drainage clear.",
                "அதிக ஈரப்பதமும் மழையும் — பூஞ்சை இலைப்புள்ளி நோயை கண்காணியுங்கள், வடிகால் தடையின்றி வைக்கவும்.",
                "अधिक नमी और बारिश — फफूंदी पत्ती धब्बा रोग की जांच करें, जल निकासी साफ़ रखें।",
            ),
        )

    return None


def build_weather(forecast: Forecast, *, source: str = SOURCE) -> WeatherBlock:
    """WeatherBlock from a live (or last-known-good) forecast.

    `source` is rendered verbatim by the home, so a stale read passes a
    stamped string here rather than silently presenting old numbers as
    current (spec §2, honest degradation).
    """
    current = forecast.current
    code = current.get("weather_code")
    icon, condition = describe(None if code is None else int(code))
    humidity = int(round(float(current.get("relative_humidity_2m") or 0)))

    return WeatherBlock(
        temp_c=round(float(current.get("temperature_2m") or 0.0), 1),
        condition_icon=icon,
        condition=condition,
        days=_days(forecast),
        humidity_pct=humidity,
        wind_kmh=int(round(float(current.get("wind_speed_10m") or 0.0))),
        wind_dir=compass(current.get("wind_direction_10m")),
        rain_chance_pct=forecast.day_rain_chance_pct[0] if forecast.day_rain_chance_pct else None,
        soil_temp_c=None if forecast.soil_temp_c is None else round(forecast.soil_temp_c, 1),
        source=source,
        advisory=_spray_advisory(forecast),
        tip=_tip(forecast, humidity),
    )


def _window(index: int) -> TranslatedText:
    hours = (index + 1) * 24
    return _t(f"next {hours} hrs", f"அடுத்த {hours} மணி நேரம்", f"अगले {hours} घंटे")


def derive_severe_alert(forecast: Forecast, district: str | None) -> SevereAlert | None:
    """Most severe qualifying condition inside the alert horizon, or None.

    Returns None far more often than not — that is the point. See the
    module docstring for why this is derived rather than relayed.
    """
    if not district:
        # The strip names a district ("Heavy rain warning — Coimbatore
        # district"). Without a resolved district there is no honest way
        # to say who the alert is for.
        return None

    horizon = min(len(forecast.days), ALERT_HORIZON_DAYS)
    best: tuple[int, int, TranslatedText] | None = None  # (rank, day index, headline)

    for index in range(horizon):
        precip = forecast.day_precip_mm[index] or 0.0
        gust = forecast.day_gust_kmh[index] or 0.0
        code = forecast.day_code[index]

        candidate: tuple[int, TranslatedText] | None = None
        if precip >= EXTREMELY_HEAVY_RAIN_MM:
            candidate = (
                4,
                _t(
                    "Extremely heavy rain warning",
                    "மிகக் கடும் மழை எச்சரிக்கை",
                    "अत्यधिक भारी बारिश की चेतावनी",
                ),
            )
        elif precip >= VERY_HEAVY_RAIN_MM:
            candidate = (
                3,
                _t("Very heavy rain warning", "மிகக் கனமழை எச்சரிக்கை", "अति भारी बारिश की चेतावनी"),
            )
        elif precip >= HEAVY_RAIN_MM:
            candidate = (
                2,
                _t("Heavy rain warning", "கனமழை எச்சரிக்கை", "भारी बारिश की चेतावनी"),
            )

        if gust >= GALE_GUST_KMH:
            gale = (
                3,
                _t("Gale-force wind warning", "பலத்த காற்று எச்சரிக்கை", "तेज़ आंधी की चेतावनी"),
            )
            if candidate is None or gale[0] > candidate[0]:
                candidate = gale

        if code is not None and int(code) == 99:
            hail = (
                3,
                _t(
                    "Severe thunderstorm with hail",
                    "ஆலங்கட்டியுடன் கடும் இடிமழை",
                    "ओलों के साथ भीषण तूफ़ान",
                ),
            )
            if candidate is None or hail[0] > candidate[0]:
                candidate = hail

        if candidate is not None and (best is None or candidate[0] > best[0]):
            best = (candidate[0], index, candidate[1])

    if best is None:
        return None

    _rank, day_index, headline = best
    return SevereAlert(
        headline=headline,
        district=district,
        window=_window(day_index),
        source=ALERT_SOURCE,
        details_url=None,
    )


def rainfall_7d_mm(forecast: Forecast) -> float | None:
    """Observed rainfall over the preceding week.

    NOT in the frozen A-U2 contract and deliberately not added to it:
    the A1 design has no element for it (see the A-U2 CP1 note). It is
    computed because it is real and cheap, and because the commodity and
    weather surfaces in W3 can use it once the owner decides whether it
    should be visible.
    """
    if not forecast.past_precip_mm:
        return None
    return round(sum(forecast.past_precip_mm), 1)


def now_ist() -> datetime:
    return datetime.now(UTC).astimezone(IST)


def stamp(moment: datetime) -> str:
    """Human as-of stamp in IST, e.g. '6:00 AM'. The UI never formats
    times itself — the stamp is data (A-U1 contract).

    Built by hand rather than with strftime("%-I:%M %p"): the no-pad
    flag is glibc-only and raises on the Windows CRT, so the dev box and
    CI would disagree.
    """
    local = moment.astimezone(IST)
    return f"{(local.hour % 12) or 12}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def day_stamp(moment: datetime) -> str:
    """Date-qualified stamp for stale reads, e.g. '15 Aug 6:00 AM'."""
    local = moment.astimezone(IST)
    return f"{local.day} {local:%b} {stamp(local)}"
