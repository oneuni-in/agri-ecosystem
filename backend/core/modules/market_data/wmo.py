"""WMO 4677 weather-code lexicon: code -> icon + {en, ta, hi} label.

A-U2 W1. This is a TRANSLATION TABLE, not data: Open-Meteo reports a
numeric weather code and we render the farmer-facing words for it. The
numbers always come from the API; only the wording lives here, in the
three locales the E5 TranslatedText convention requires.

Icons stay inside the A1 FINAL v4 set the A-U1 fixtures established
(sun / part-cloud / cloud / fog / drizzle / rain / storm), so a real
forecast renders with the same glyph vocabulary the mockup was drawn
against.

Snow and freezing codes cannot occur in the Tamil Nadu launch geography
but are mapped anyway: an unmapped code would otherwise fall to the
UNKNOWN entry and show a farmer a shrug where the API gave us an answer.
"""

from __future__ import annotations

from .schemas import TranslatedText


def _t(en: str, ta: str, hi: str) -> TranslatedText:
    return TranslatedText(en=en, ta=ta, hi=hi)


# code -> (icon, label). Groupings follow the WMO 4677 present-weather
# table as published in the Open-Meteo docs.
_CODES: dict[int, tuple[str, TranslatedText]] = {
    0: ("☀️", _t("Clear sky", "வெளிப்படையான வானம்", "साफ़ आसमान")),
    1: ("🌤️", _t("Mainly clear", "பெரும்பாலும் தெளிவு", "अधिकतर साफ़")),
    2: ("⛅", _t("Partly cloudy", "பகுதி மேகமூட்டம்", "आंशिक बादल")),
    3: ("☁️", _t("Overcast", "மேகமூட்டம்", "बादल छाए")),
    45: ("🌫️", _t("Fog", "மூடுபனி", "कोहरा")),
    48: ("🌫️", _t("Rime fog", "உறை மூடுபனி", "तुषार कोहरा")),
    51: ("🌦️", _t("Light drizzle", "லேசான தூறல்", "हल्की बूंदाबांदी")),
    53: ("🌦️", _t("Drizzle", "தூறல்", "बूंदाबांदी")),
    55: ("🌧️", _t("Dense drizzle", "அடர் தூறல்", "घनी बूंदाबांदी")),
    56: ("🌧️", _t("Freezing drizzle", "உறைபனி தூறல்", "जमा देने वाली बूंदाबांदी")),
    57: ("🌧️", _t("Dense freezing drizzle", "அடர் உறைபனி தூறல்", "घनी जमने वाली बूंदाबांदी")),
    61: ("🌦️", _t("Light rain", "லேசான மழை", "हल्की बारिश")),
    63: ("🌧️", _t("Moderate rain", "மிதமான மழை", "मध्यम बारिश")),
    65: ("🌧️", _t("Heavy rain", "கனமழை", "भारी बारिश")),
    66: ("🌧️", _t("Freezing rain", "உறைபனி மழை", "जमने वाली बारिश")),
    67: ("🌧️", _t("Heavy freezing rain", "கன உறைபனி மழை", "भारी जमने वाली बारिश")),
    71: ("🌨️", _t("Light snow", "லேசான பனிப்பொழிவு", "हल्की बर्फ़बारी")),
    73: ("🌨️", _t("Moderate snow", "மிதமான பனிப்பொழிவு", "मध्यम बर्फ़बारी")),
    75: ("🌨️", _t("Heavy snow", "கன பனிப்பொழிவு", "भारी बर्फ़बारी")),
    77: ("🌨️", _t("Snow grains", "பனித்துகள்", "बर्फ़ के दाने")),
    80: ("🌦️", _t("Light showers", "லேசான தூறல் மழை", "हल्की बौछारें")),
    81: ("🌧️", _t("Showers", "தூறல் மழை", "बौछारें")),
    82: ("⛈️", _t("Violent showers", "கடும் மழை", "तेज़ बौछारें")),
    85: ("🌨️", _t("Snow showers", "பனி மழை", "बर्फ़ की बौछारें")),
    86: ("🌨️", _t("Heavy snow showers", "கன பனி மழை", "भारी बर्फ़ की बौछारें")),
    95: ("⛈️", _t("Thunderstorm", "இடியுடன் மழை", "गरज के साथ बारिश")),
    96: ("⛈️", _t("Thunderstorm with hail", "ஆலங்கட்டியுடன் இடிமழை", "ओलों के साथ तूफ़ान")),
    99: ("⛈️", _t("Severe thunderstorm with hail", "கடும் ஆலங்கட்டி இடிமழை", "भीषण ओलावृष्टि")),
}

# Served when the API sends a code outside the published table. Says
# "we don't know" rather than guessing a condition (no invented data).
UNKNOWN: tuple[str, TranslatedText] = (
    "🌡️",
    _t("Conditions unavailable", "நிலவரம் இல்லை", "स्थिति उपलब्ध नहीं"),
)


def describe(code: int | None) -> tuple[str, TranslatedText]:
    """(icon, label) for a WMO code; UNKNOWN for anything unmapped."""
    if code is None:
        return UNKNOWN
    return _CODES.get(int(code), UNKNOWN)


def is_wet(code: int | None) -> bool:
    """True for any precipitating code — the spray-advisory input."""
    if code is None:
        return False
    return int(code) >= 51


# Weekday labels for the 7-day strip. Short forms: the A1 strip is a
# 7-across row on a 360px phone, so these must stay 2-4 glyphs (the
# A-U1 fixtures set the precedent: "Sat"/"சனி"/"शनि").
WEEKDAYS: tuple[TranslatedText, ...] = (
    _t("Mon", "திங்", "सोम"),
    _t("Tue", "செவ்", "मंगल"),
    _t("Wed", "புத", "बुध"),
    _t("Thu", "வியா", "गुरु"),
    _t("Fri", "வெள்", "शुक्र"),
    _t("Sat", "சனி", "शनि"),
    _t("Sun", "ஞாயி", "रवि"),
)

TODAY_LABEL: TranslatedText = _t("Today", "இன்று", "आज")

# 16-point compass, index = round(degrees / 22.5) % 16. The contract
# renders wind_dir verbatim next to the speed ("12 km/h SW").
COMPASS: tuple[str, ...] = (
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
)


def compass(degrees: float | None) -> str:
    if degrees is None:
        return ""
    return COMPASS[round(float(degrees) / 22.5) % 16]
