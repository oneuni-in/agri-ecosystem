"""A-U1 W3 — deterministic stub fixtures for GET /market/today/{pincode}.

STUB-UNTIL-A-U2. The values are the A1 FINAL v4 reference's sample data
(Coimbatore), byte-stable across calls so e2e specs can assert exact DOM.
They are served ONLY behind the agri_today flag, which stays OFF in prod
until A-U2 replaces this module's fixtures with real workers (Open-Meteo
D42, Agmarknet D43). `stub=True` travels in the payload so no surface can
mistake fixture data for market truth.
"""

from __future__ import annotations

from datetime import date

from .schemas import (
    CalendarBlock,
    CalendarMonth,
    CropWindow,
    DailyTip,
    MandiBlock,
    MandiCommodity,
    SchemeDeadline,
    SchemeItem,
    SchemesBlock,
    SevereAlert,
    TodayPayload,
    TranslatedText,
    WeatherAdvisory,
    WeatherBlock,
    WeatherDay,
)

# The stub is frozen in time on purpose (deterministic e2e); A-U2 workers
# stamp real times.
_GENERATED_AT = "2026-08-15T06:00:00+05:30"


def _t(en: str, ta: str, hi: str) -> TranslatedText:
    return TranslatedText(en=en, ta=ta, hi=hi)


def _weather() -> WeatherBlock:
    days = [
        WeatherDay(label=_t("Today", "இன்று", "आज"), icon="🌦️", high_c=29, low_c=22),
        WeatherDay(label=_t("Sat", "சனி", "शनि"), icon="⛅", high_c=31, low_c=23),
        WeatherDay(label=_t("Sun", "ஞாயி", "रवि"), icon="☀️", high_c=32, low_c=23),
        WeatherDay(label=_t("Mon", "திங்", "सोम"), icon="☀️", high_c=33, low_c=24),
        WeatherDay(label=_t("Tue", "செவ்", "मंगल"), icon="⛅", high_c=31, low_c=23),
        WeatherDay(label=_t("Wed", "புத", "बुध"), icon="🌧️", high_c=28, low_c=22),
        WeatherDay(label=_t("Thu", "வியா", "गुरु"), icon="⛈️", high_c=27, low_c=21),
    ]
    return WeatherBlock(
        temp_c=29,
        condition_icon="🌦️",
        condition=_t("Light rain from Thu", "வியாழன் முதல் லேசான மழை", "गुरुवार से हल्की बारिश"),
        days=days,
        humidity_pct=78,
        wind_kmh=12,
        wind_dir="SW",
        rain_chance_pct=85,
        soil_temp_c=26,
        source="Open-Meteo · IMD alerts (stub)",
        advisory=WeatherAdvisory(
            kind="spray",
            title=_t("Spray window advisory", "தெளிப்பு நேர அறிவுரை", "छिड़काव सलाह"),
            body=_t(
                "Good spraying conditions till Tuesday evening. "
                "Avoid Wed–Thu — rain likely to wash off application.",
                "செவ்வாய் மாலை வரை தெளிக்கலாம். புதன்–வியாழன் மழை வரும் — தெளிக்க வேண்டாம்.",
                "मंगलवार शाम तक छिड़काव ठीक। बुध–गुरु बारिश से बचें।",
            ),
        ),
        tip=DailyTip(
            title=_t("Tip of the day", "இன்றைய குறிப்பு", "आज का सुझाव"),
            body=_t(
                "Rain coming Thursday — postpone urea top-dressing; applying "
                "before heavy rain loses up to 40% nitrogen to runoff.",
                "வியாழன் மழை — யூரியா இடுவதை தள்ளிப்போடுங்கள்; கனமழைக்கு முன் இட்டால் 40% நைட்ரஜன் வீணாகும்.",
                "गुरुवार को बारिश — यूरिया टॉप-ड्रेसिंग टालें; भारी बारिश से 40% नाइट्रोजन बह जाता है।",
            ),
        ),
    )


def _mandi() -> MandiBlock:
    c = [
        MandiCommodity(
            slug="tomato",
            name=_t("Tomato", "தக்காளி", "टमाटर"),
            emoji="🍅",
            market="Coimbatore market",
            unit="kg",
            price=28,
            change=4,
            series_30d=[20, 21, 20, 22, 22, 24, 23, 26, 28],
            range_low=18,
            range_high=29,
            modal=24,
            arrivals_qtl=12400,
        ),
        MandiCommodity(
            slug="onion",
            name=_t("Onion", "வெங்காயம்", "प्याज़"),
            emoji="🧅",
            market="Coimbatore market",
            unit="kg",
            price=26,
            change=-2,
            series_30d=[32, 31, 31, 29, 30, 28, 28, 27, 26],
            range_low=24,
            range_high=34,
            modal=29,
            arrivals_qtl=8150,
        ),
        MandiCommodity(
            slug="paddy",
            name=_t("Paddy (common)", "நெல்", "धान"),
            emoji="🌾",
            market="Coimbatore market",
            unit="kg",
            price=23,
            change=0,
            series_30d=[23, 23, 22, 23, 23, 23, 22, 23, 23],
            range_low=22,
            range_high=24,
            note=_t("MSP ₹24.3", "MSP ₹24.3", "MSP ₹24.3"),
        ),
        MandiCommodity(
            slug="turmeric",
            name=_t("Turmeric", "மஞ்சள்", "हल्दी"),
            emoji="🟡",
            market="Erode market",
            unit="kg",
            price=142,
            change=6,
            series_30d=[118, 122, 121, 128, 126, 132, 138, 139, 142],
            range_low=118,
            range_high=145,
            note=_t("export demand ↑", "ஏற்றுமதி தேவை ↑", "निर्यात मांग ↑"),
        ),
        MandiCommodity(
            slug="coconut",
            name=_t("Coconut", "தேங்காய்", "नारियल"),
            emoji="🥥",
            market="Pollachi market",
            unit="pc",
            price=38,
            change=1,
            series_30d=[33, 34, 33, 35, 34, 36, 36, 37, 38],
            range_low=33,
            range_high=39,
            note=_t("copra firm", "கொப்பரை உறுதி", "खोपरा स्थिर"),
        ),
        MandiCommodity(
            slug="banana",
            name=_t("Banana (nendran)", "வாழை", "केला"),
            emoji="🍌",
            market="Coimbatore market",
            unit="kg",
            price=32,
            change=1,
            series_30d=[27, 28, 28, 29, 29, 30, 30, 31, 32],
            range_low=27,
            range_high=33,
            note=_t("festival demand", "பண்டிகை தேவை", "त्योहारी मांग"),
        ),
        MandiCommodity(
            slug="groundnut",
            name=_t("Groundnut", "நிலக்கடலை", "मूंगफली"),
            emoji="🥜",
            market="Tiruppur market",
            unit="kg",
            price=68,
            change=3,
            series_30d=[58, 60, 59, 62, 63, 62, 65, 66, 68],
            range_low=58,
            range_high=69,
            note=_t("oil mills buying", "எண்ணெய் ஆலைகள்", "तेल मिलें खरीद रहीं"),
        ),
        MandiCommodity(
            slug="dry-chilli",
            name=_t("Dry chilli", "காய்ந்த மிளகாய்", "सूखी मिर्च"),
            emoji="🌶️",
            market="Coimbatore market",
            unit="kg",
            price=186,
            change=-4,
            series_30d=[214, 210, 206, 202, 200, 196, 192, 190, 186],
            range_low=180,
            range_high=214,
            note=_t("arrivals up", "வரத்து அதிகம்", "आवक बढ़ी"),
        ),
    ]
    return MandiBlock(
        market="Coimbatore market", as_of="6:00 AM", source="Agmarknet (stub)", commodities=c
    )


def _calendar() -> CalendarBlock:
    months = [
        CalendarMonth(label="Jun", in_season=False, current=False),
        CalendarMonth(label="Jul", in_season=True, current=False),
        CalendarMonth(label="Aug", in_season=True, current=True),
        CalendarMonth(label="Sep", in_season=True, current=False),
        CalendarMonth(label="Oct", in_season=True, current=False),
        CalendarMonth(label="Nov", in_season=False, current=False),
        CalendarMonth(label="Dec", in_season=False, current=False),
        CalendarMonth(label="Jan", in_season=False, current=False),
    ]
    return CalendarBlock(
        zone=_t("TN west zone", "தமிழ்நாடு மேற்கு மண்டலம்", "तमिलनाडु पश्चिम क्षेत्र"),
        months=months,
        sowing=[
            CropWindow(
                icon="🌾",
                label=_t("Samba paddy", "சம்பா நெல்", "सांबा धान"),
                until=_t("till 25 Aug", "ஆக 25 வரை", "25 अग तक"),
            ),
            CropWindow(
                icon="🌽",
                label=_t("Maize", "மக்காச்சோளம்", "मक्का"),
                until=_t("till 30 Aug", "ஆக 30 வரை", "30 अग तक"),
            ),
            CropWindow(
                icon="🥜",
                label=_t("Groundnut (rainfed)", "நிலக்கடலை", "मूंगफली"),
                until=_t("till 20 Aug", "ஆக 20 வரை", "20 अग तक"),
            ),
            CropWindow(
                icon="🫘",
                label=_t("Black gram", "உளுந்து", "उड़द"),
                until=_t("till 5 Sep", "செப 5 வரை", "5 सित तक"),
            ),
        ],
        harvesting=[
            CropWindow(
                icon="🧅",
                label=_t("Kharif onion", "கார் வெங்காயம்", "खरीफ प्याज़"),
                until=_t("early lots", "முன் அறுவடை", "शुरुआती"),
            ),
            CropWindow(
                icon="🍌",
                label=_t("Banana", "வாழை", "केला"),
                until=_t("year-round", "ஆண்டு முழுவதும்", "सालभर"),
            ),
        ],
    )


def _schemes() -> SchemesBlock:
    return SchemesBlock(
        items=[
            SchemeItem(
                level="central",
                title=_t("PM-Kisan Samman Nidhi", "பிஎம்-கிசான்", "पीएम-किसान सम्मान निधि"),
                body=_t(
                    "₹6,000/year in three instalments, direct to bank. "
                    "18th instalment being credited now.",
                    "ஆண்டுக்கு ₹6,000 மூன்று தவணைகளில். 18வது தவணை வரவு வைக்கப்படுகிறது.",
                    "₹6,000/वर्ष तीन किस्तों में, सीधे बैंक में। 18वीं किस्त जारी।",
                ),
                verified_against="pmkisan.gov.in",
                verified_on=date(2026, 8, 12),
                url="https://pmkisan.gov.in/",
                link_label=_t("Check status & guide", "நிலை அறிக", "स्थिति देखें"),
            ),
            SchemeItem(
                level="central",
                title=_t("PMFBY crop insurance", "PMFBY பயிர் காப்பீடு", "PMFBY फसल बीमा"),
                body=_t(
                    "Kharif 2026 enrolment window open till 31 Aug. Premium: 2% for food crops.",
                    "காரீஃப் 2026 பதிவு ஆக 31 வரை. உணவுப் பயிர்களுக்கு 2% பிரீமியம்.",
                    "खरीफ 2026 नामांकन 31 अग तक। खाद्य फसलों के लिए 2% प्रीमियम।",
                ),
                verified_against="pmfby.gov.in",
                verified_on=date(2026, 8, 10),
                url="https://pmfby.gov.in/",
                link_label=_t("Am I covered?", "காப்பீடு உள்ளதா?", "क्या मैं कवर हूं?"),
            ),
            SchemeItem(
                level="state",
                state_label=_t("TN State", "தமிழ்நாடு", "तमिलनाडु"),
                title=_t(
                    "100% drip irrigation subsidy", "சொட்டு நீர் 100% மானியம்", "ड्रिप सिंचाई 100% सब्सिडी"
                ),
                body=_t(
                    "Small & marginal farmers, per-hectare cap. Apply via block agri office.",
                    "சிறு விவசாயிகளுக்கு. வட்டார வேளாண் அலுவலகத்தில் விண்ணப்பிக்கவும்.",
                    "छोटे किसानों के लिए। ब्लॉक कृषि कार्यालय से आवेदन करें।",
                ),
                verified_against="tnhorticulture.tn.gov.in",
                verified_on=date(2026, 8, 8),
                url="https://tnhorticulture.tn.gov.in/",
                link_label=_t("Eligibility & documents", "தகுதி விவரம்", "पात्रता व दस्तावेज़"),
            ),
        ],
        deadlines=[
            SchemeDeadline(
                chip="20 AUG",
                title=_t("KCC saturation camp", "KCC முகாம்", "KCC शिविर"),
                note=_t("block offices", "வட்டார அலுவலகம்", "ब्लॉक कार्यालय"),
            ),
            SchemeDeadline(
                chip="31 AUG",
                title=_t(
                    "PMFBY Kharif enrolment closes", "PMFBY பதிவு முடிவு", "PMFBY नामांकन समाप्त"
                ),
            ),
            SchemeDeadline(
                chip="15 SEP",
                title=_t("Drone subsidy", "ட்ரோன் மானியம்", "ड्रोन सब्सिडी"),
                note=_t("FPO applications", "FPO விண்ணப்பம்", "FPO आवेदन"),
            ),
            SchemeDeadline(
                chip="72 HRS",
                title=_t("PMFBY crop-loss intimation", "பயிர் சேத அறிவிப்பு", "फसल क्षति सूचना"),
                note=_t(
                    "call 14447 within 72 hrs of damage",
                    "சேதம் ஏற்பட்ட 72 மணி நேரத்தில் 14447",
                    "क्षति के 72 घंटे में 14447",
                ),
            ),
        ],
    )


def today_fixture(pincode: str) -> TodayPayload:
    return TodayPayload(
        pincode=pincode,
        # The stub knows only the reference district; A-U2 resolves real geo.
        district="Coimbatore" if pincode.startswith("641") else None,
        generated_at=_GENERATED_AT,
        stub=True,
        weather=_weather(),
        severe_alert=SevereAlert(
            headline=_t("Heavy rain warning", "கனமழை எச்சரிக்கை", "भारी बारिश की चेतावनी"),
            district="Coimbatore",
            window=_t("next 48 hrs", "அடுத்த 48 மணி நேரம்", "अगले 48 घंटे"),
            source="IMD (stub)",
        )
        if pincode.startswith("641")
        else None,
        mandi=_mandi(),
        calendar=_calendar(),
        schemes=_schemes(),
    )
