"""Seed the livestock/poultry care pack and the pest-advisory example.

    python -m scripts.seed_content_packs

A SCRIPT, not a migration, on purpose: 0045 seeded `content.sources`
because a curated feed list is configuration, but these are CONTENT.
Content gets edited, superseded and added to continuously, and freezing
editorial prose into a numbered migration makes the next edit a schema
change. Idempotent on slug, so re-running is safe.

EVERYTHING SEEDED HERE LANDS `pending`.

That is not caution, it is the rule doing its job. `create_item()` strips
`moderation_status`, so this script *cannot* publish even if it tried.
Livestock care and pest advisories are the exact category the constitution
singles out — the dosage/scheme/loan rule — and this text was drafted by
an agent, not written by a vet or an entomologist. It must be read by a
human before a farmer sees it.

So the copy below deliberately stays on the safe side of that line:
- SCOUTING and HUSBANDRY practice — what to look for, when to look,
  what conditions to keep — which is observational and low-risk.
- NO chemical names, NO dosages, NO spray concentrations, NO vaccination
  schedules. Every guide routes the reader to the Kisan Call Centre or
  their vet for the treatment decision, because that decision needs
  someone who can see the animal or the field.

Sources are named per item and are the real ones (ICAR/DAHD/TNAU
extension material). `source_url` points at the institution, not at a
specific page we might be paraphrasing.
"""

import asyncio
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from modules.content.models import KIND_ADVISORY, KIND_GUIDE, ContentItem  # noqa: E402
from modules.content.service import create_item  # noqa: E402
from settings import get_settings  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402
from shared.telemetry import configure_logging  # noqa: E402

# Publisher date for first-party editorial: the day it was drafted.
DRAFTED = datetime(2026, 8, 17, tzinfo=UTC)

PACKS: list[dict[str, Any]] = [
    {
        "kind": KIND_GUIDE,
        "slug": "dairy-cattle-heat-stress-care",
        "verticals": ["livestock", "dairy"],
        "language": "en",
        "source_name": "agri.in · ICAR extension guidance",
        "source_url": "https://icar.org.in/",
        "title": {
            "en": "Keeping dairy cattle comfortable in the hot months",
            "ta": "வெயில் காலத்தில் கறவை மாடுகளை வசதியாக வைத்திருத்தல்",
            "hi": "गर्मी के महीनों में दुधारू पशुओं को आरामदायक रखना",
        },
        "summary": {
            "en": "Shade, water and airflow decide how much milk you lose to a hot week.",
            "ta": "நிழல், தண்ணீர், காற்றோட்டம் — வெப்பமான வாரத்தில் பால் இழப்பை இவை தீர்மானிக்கின்றன.",
            "hi": "छाया, पानी और हवा तय करते हैं कि गर्म सप्ताह में कितना दूध घटेगा।",
        },
        "body": {
            "en": (
                "Milk yield falls before an animal looks unwell. Watch for panting, "
                "drooling and standing rather than lying down — these show up a day "
                "or two before the milk drops.\n\n"
                "What helps most, in order:\n"
                "• Shade over the standing area, not just the shed. A tree or a "
                "thatch extension costs little and does more than a fan.\n"
                "• Clean water within reach at all times. Cattle drink far more in "
                "heat, and they will not walk far for it in the afternoon.\n"
                "• Airflow through the shed. Open the sides if you can; still air "
                "under a tin roof is worse than open sun with a breeze.\n"
                "• Feed the heavier ration early morning and after sunset. Digestion "
                "itself generates heat.\n"
                "• Bathe or sprinkle in the afternoon where water allows.\n\n"
                "If an animal stops ruminating, refuses water, or the yield drops "
                "sharply in one day, call your veterinarian or the Kisan Call Centre "
                "(1800-180-1551). Do not start any medicine on your own — that "
                "decision needs someone who can examine the animal."
            ),
            "ta": (
                "விலங்கு நோய்வாய்ப்பட்டதாகத் தெரிவதற்கு முன்பே பால் அளவு குறையும். "
                "மூச்சிரைப்பு, எச்சில் வடிதல், படுக்காமல் நிற்பது — இவை பால் குறைவதற்கு "
                "ஒன்றிரண்டு நாட்கள் முன்பே தெரியும்.\n\n"
                "முக்கியமானவை, வரிசைப்படி:\n"
                "• கொட்டகைக்கு மட்டுமல்ல, நிற்கும் இடத்திற்கும் நிழல். மரம் அல்லது ஓலைக் "
                "கூரை குறைந்த செலவில் மின்விசிறியை விட அதிகம் உதவும்.\n"
                "• எப்போதும் கைக்கெட்டும் தூரத்தில் சுத்தமான தண்ணீர். வெயிலில் மாடுகள் "
                "அதிகம் குடிக்கும்; மதியத்தில் தூரம் நடக்காது.\n"
                "• கொட்டகையில் காற்றோட்டம். முடிந்தால் பக்கங்களைத் திறந்து விடுங்கள்.\n"
                "• கனமான தீவனத்தை அதிகாலையிலும் சூரியன் மறைந்த பின்பும் கொடுங்கள்.\n"
                "• தண்ணீர் வசதி இருந்தால் மதியம் குளிப்பாட்டுங்கள்.\n\n"
                "அசைபோடுவதை நிறுத்தினால், தண்ணீர் குடிக்க மறுத்தால், அல்லது ஒரே நாளில் "
                "பால் கூர்மையாகக் குறைந்தால் — கால்நடை மருத்துவரையோ விவசாயி அழைப்பு "
                "மையத்தையோ (1800-180-1551) அணுகுங்கள். நீங்களாகவே எந்த மருந்தையும் "
                "தொடங்க வேண்டாம்."
            ),
            "hi": (
                "पशु के बीमार दिखने से पहले ही दूध घटने लगता है। हाँफना, लार गिरना और "
                "बैठने के बजाय खड़े रहना — ये दूध घटने से एक-दो दिन पहले दिखते हैं।\n\n"
                "सबसे ज़्यादा काम की बातें, क्रम में:\n"
                "• सिर्फ़ शेड नहीं, खड़े होने की जगह पर भी छाया। पेड़ या छप्पर पंखे से "
                "ज़्यादा असर करता है और खर्च कम है।\n"
                "• हर समय पहुँच में साफ़ पानी। गर्मी में पशु कहीं ज़्यादा पीते हैं और "
                "दोपहर में दूर तक नहीं जाएँगे।\n"
                "• शेड में हवा का बहाव। हो सके तो किनारे खुले रखें।\n"
                "• भारी आहार सुबह जल्दी और सूरज ढलने के बाद दें।\n"
                "• पानी हो तो दोपहर में नहलाएँ या छिड़काव करें।\n\n"
                "अगर पशु जुगाली बंद कर दे, पानी न पिए, या एक ही दिन में दूध तेज़ी से गिरे "
                "— पशु चिकित्सक या किसान कॉल सेंटर (1800-180-1551) से संपर्क करें। "
                "अपने आप कोई दवा शुरू न करें।"
            ),
        },
    },
    {
        "kind": KIND_GUIDE,
        "slug": "backyard-poultry-first-six-weeks",
        "verticals": ["poultry", "livestock"],
        "language": "en",
        "source_name": "agri.in · DAHD backyard poultry guidance",
        "source_url": "https://dahd.gov.in/",
        "title": {
            "en": "Backyard poultry: getting the first six weeks right",
            "ta": "வீட்டுக் கோழி வளர்ப்பு: முதல் ஆறு வாரங்கள்",
            "hi": "घरेलू मुर्गीपालन: पहले छह हफ़्ते",
        },
        "summary": {
            "en": "Most backyard flock losses happen before week six, and most are preventable.",
            "ta": (
                "வீட்டுக் கோழிகளின் பெரும்பாலான இழப்புகள் ஆறாவது வாரத்திற்குள் "
                "நிகழ்கின்றன — பெரும்பாலும் தவிர்க்கக்கூடியவை."
            ),
            "hi": "घरेलू मुर्गियों का अधिकांश नुकसान छठे हफ़्ते से पहले होता है, और अधिकतर रोका जा सकता है।",
        },
        "body": {
            "en": (
                "Chicks cannot regulate their own temperature for the first three "
                "weeks. Almost everything that goes wrong early traces back to being "
                "too cold, too crowded, or drinking dirty water.\n\n"
                "• Warmth: chicks spread out evenly when the temperature is right. "
                "Huddled in a tight ball means too cold; pressed to the edges away "
                "from the heat means too hot. Read the chicks, not the thermometer.\n"
                "• Space: crowding causes pecking, and pecking wounds invite "
                "infection. Give more floor as they grow.\n"
                "• Water: change it daily and keep the drinker off the litter. Wet, "
                "caked litter is the single most common source of early trouble.\n"
                "• Litter: keep it dry and loose. Damp litter chills chicks from "
                "below even in a warm room.\n"
                "• Predators and rats take more birds at night than disease does in "
                "many backyard flocks. Close the shelter properly after dusk.\n\n"
                "Vaccination is essential, but the schedule depends on your area and "
                "on what your hatchery has already given. Ask your local veterinary "
                "dispensary or the animal husbandry helpline (1962) — do not follow a "
                "schedule found online."
            ),
            "ta": (
                "முதல் மூன்று வாரங்களுக்குக் குஞ்சுகளால் தங்கள் உடல் வெப்பத்தைக் கட்டுப்படுத்த "
                "முடியாது. ஆரம்பத்தில் ஏற்படும் பிரச்சினைகள் அனைத்தும் — குளிர், நெரிசல், "
                "அசுத்தமான தண்ணீர் — இவற்றிலிருந்தே வருகின்றன.\n\n"
                "• வெப்பம்: சரியான வெப்பநிலையில் குஞ்சுகள் சமமாகப் பரவியிருக்கும். ஒன்றாகக் "
                "கூடி நிற்றல் = குளிர்; விளிம்புகளை நோக்கி விலகுதல் = அதிக வெப்பம். "
                "வெப்பமானியை அல்ல, குஞ்சுகளைப் படியுங்கள்.\n"
                "• இடம்: நெரிசல் கொத்துதலை உண்டாக்கும்; காயங்கள் தொற்றுக்கு வழிவகுக்கும்.\n"
                "• தண்ணீர்: தினமும் மாற்றுங்கள்; தண்ணீர்த் தொட்டியை விரிப்பின் மேல் "
                "வைக்காதீர்கள். ஈரமான விரிப்புதான் ஆரம்பகாலப் பிரச்சினைகளின் முதன்மைக் காரணம்.\n"
                "• விரிப்பு: உலர்ந்தும் தளர்வாகவும் இருக்கட்டும்.\n"
                "• பல வீட்டுப் பண்ணைகளில் நோயை விட இரவு நேர வேட்டையாடிகளும் எலிகளும் "
                "அதிகக் கோழிகளை இழக்கச் செய்கின்றன. மாலைக்குப் பின் கொட்டகையை மூடுங்கள்.\n\n"
                "தடுப்பூசி அவசியம், ஆனால் அட்டவணை உங்கள் பகுதியையும் குஞ்சு விற்பனையகம் "
                "ஏற்கனவே போட்டதையும் பொறுத்தது. அருகிலுள்ள கால்நடை மருத்துவமனையையோ "
                "உதவி எண்ணையோ (1962) கேளுங்கள் — இணையத்தில் கிடைக்கும் அட்டவணையைப் "
                "பின்பற்ற வேண்டாம்."
            ),
            "hi": (
                "चूज़े पहले तीन हफ़्ते अपना तापमान खुद नियंत्रित नहीं कर सकते। शुरुआती "
                "गड़बड़ियों की जड़ लगभग हमेशा ठंड, भीड़ या गंदा पानी होती है।\n\n"
                "• गर्माहट: तापमान सही हो तो चूज़े एक-समान फैले रहते हैं। गुच्छा बनाकर "
                "बैठना = ठंड; किनारों पर हटना = ज़्यादा गर्मी। थर्मामीटर नहीं, चूज़ों को "
                "पढ़िए।\n"
                "• जगह: भीड़ से चोंच मारना शुरू होता है और घाव संक्रमण को बुलाते हैं।\n"
                "• पानी: रोज़ बदलें और बर्तन बिछावन से ऊपर रखें। गीला बिछावन शुरुआती "
                "परेशानी का सबसे आम कारण है।\n"
                "• बिछावन: सूखा और भुरभुरा रखें।\n"
                "• कई घरेलू झुंडों में बीमारी से ज़्यादा नुकसान रात के शिकारी और चूहे "
                "करते हैं। शाम ढलते ही दरबा ठीक से बंद करें।\n\n"
                "टीकाकरण ज़रूरी है, पर समय-सारणी आपके क्षेत्र और हैचरी पर निर्भर करती है। "
                "नज़दीकी पशु चिकित्सालय या पशुपालन हेल्पलाइन (1962) से पूछें — इंटरनेट "
                "पर मिली सारणी का पालन न करें।"
            ),
        },
    },
]

# One REAL advisory, targeted. Fall armyworm in maize is well documented
# by ICAR-NBAIR and state extension services, and the window below is the
# Tamil Nadu kharif maize scouting period. Scouting guidance only — the
# control decision is explicitly routed to a human.
ADVISORIES: list[dict[str, Any]] = [
    {
        "kind": KIND_ADVISORY,
        "slug": "fall-armyworm-maize-scouting-aug-2026",
        "verticals": ["crop-protection", "maize"],
        "language": "en",
        "source_name": "agri.in · ICAR-NBAIR pest advisory guidance",
        "source_url": "https://icar.org.in/",
        # The targeting that makes this an ALERT and not a notice.
        "districts": ["Coimbatore", "Erode", "Salem", "Dharmapuri", "Krishnagiri"],
        "window_start": date(2026, 8, 1),
        "window_end": date(2026, 9, 30),
        "title": {
            "en": "Check young maize for fall armyworm this fortnight",
            "ta": "இந்தப் பதினைந்து நாட்களில் இளம் மக்காச்சோளத்தில் படைப்புழுவைப் பாருங்கள்",
            "hi": "इस पखवाड़े छोटी मक्का में फ़ॉल आर्मीवर्म देखें",
        },
        "summary": {
            "en": (
                "Ragged holes in the whorl and moist sawdust-like frass mean the pest "
                "is already inside."
            ),
            "ta": "சுருள் இலையில் ஒழுங்கற்ற துளைகளும், ஈரமான மரத்தூள் போன்ற கழிவும் — பூச்சி உள்ளே இருக்கிறது.",
            "hi": "गोभ में कटे-फटे छेद और गीले बुरादे जैसा मल — कीट अंदर पहुँच चुका है।",
        },
        "body": {
            "en": (
                "Maize between emergence and the whorl stage is most at risk. Walk "
                "the field twice a week and look at 10 plants in each of 5 spots.\n\n"
                "What to look for:\n"
                "• Small 'window pane' patches where the leaf surface is scraped but "
                "not holed — this is the earliest sign.\n"
                "• Ragged, irregular holes in the whorl leaves.\n"
                "• Moist frass that looks like wet sawdust at the base of the whorl. "
                "Dry frass usually means the larva has already moved on.\n"
                "• An inverted Y mark on the head of the larva, and four dots in a "
                "square on the second-last segment — that identifies fall armyworm "
                "rather than a look-alike.\n\n"
                "Count the plants showing damage out of the 50 you checked. That "
                "percentage — not the sight of one caterpillar — is what a control "
                "decision is based on.\n\n"
                "Take that count to your agriculture extension officer or the Kisan "
                "Call Centre (1800-180-1551) before spraying anything. What to use, "
                "and whether to use anything at all, depends on the crop stage and "
                "the damage level, and this page will not name a chemical or a dose."
            ),
            "ta": (
                "முளைத்த நாள் முதல் சுருள் நிலை வரை மக்காச்சோளத்திற்கு அதிக ஆபத்து. "
                "வாரம் இருமுறை வயலைச் சுற்றி, 5 இடங்களில் தலா 10 செடிகளைப் பாருங்கள்.\n\n"
                "என்ன பார்க்க வேண்டும்:\n"
                "• இலை மேற்பரப்பு சுரண்டப்பட்டு துளையாகாத சிறிய 'ஜன்னல்' திட்டுகள் — "
                "இதுவே ஆரம்ப அறிகுறி.\n"
                "• சுருள் இலைகளில் ஒழுங்கற்ற துளைகள்.\n"
                "• சுருளின் அடிப்பகுதியில் ஈரமான மரத்தூள் போன்ற கழிவு. உலர்ந்த கழிவு "
                "என்றால் புழு நகர்ந்திருக்கும்.\n"
                "• புழுவின் தலையில் தலைகீழ் Y குறியும், கடைசிக்கு முந்தைய கண்டத்தில் "
                "சதுரமாக நான்கு புள்ளிகளும் — இவை படைப்புழுவை உறுதிப்படுத்தும்.\n\n"
                "பார்த்த 50 செடிகளில் எத்தனையில் சேதம் உள்ளது என்று எண்ணுங்கள். ஒரு "
                "புழுவைப் பார்ப்பது அல்ல, அந்த சதவீதமே கட்டுப்பாட்டு முடிவுக்கு அடிப்படை.\n\n"
                "எதையும் தெளிப்பதற்கு முன் அந்த எண்ணிக்கையை வேளாண் விரிவாக்க அலுவலரிடமோ "
                "விவசாயி அழைப்பு மையத்திடமோ (1800-180-1551) சொல்லுங்கள். இந்தப் பக்கம் "
                "எந்த மருந்தையும் அளவையும் குறிப்பிடாது."
            ),
            "hi": (
                "अंकुरण से गोभ अवस्था तक मक्का को सबसे ज़्यादा ख़तरा है। हफ़्ते में दो बार "
                "खेत घूमें और 5 जगहों पर 10-10 पौधे देखें।\n\n"
                "क्या देखें:\n"
                "• छोटे 'खिड़की' जैसे धब्बे जहाँ पत्ती की सतह खुरची हो पर छेद न हो — "
                "यही सबसे पहला संकेत है।\n"
                "• गोभ की पत्तियों में कटे-फटे अनियमित छेद।\n"
                "• गोभ के आधार पर गीले बुरादे जैसा मल। सूखा मल आमतौर पर मतलब सूँडी "
                "आगे बढ़ चुकी है।\n"
                "• सूँडी के सिर पर उल्टा Y और अंतिम से पहले खंड पर वर्ग में चार बिंदु — "
                "इससे फ़ॉल आर्मीवर्म की पहचान होती है।\n\n"
                "देखे गए 50 पौधों में से कितने में नुकसान है, यह गिनें। एक सूँडी दिख जाना "
                "नहीं, यही प्रतिशत नियंत्रण के फ़ैसले का आधार है।\n\n"
                "कुछ भी छिड़कने से पहले यह गिनती अपने कृषि विस्तार अधिकारी या किसान कॉल "
                "सेंटर (1800-180-1551) को बताएँ। यह पृष्ठ न कोई दवा बताएगा न मात्रा।"
            ),
        },
    },
]


async def main() -> int:
    created = skipped = 0
    async with get_sessionmaker()() as session:
        for spec in [*PACKS, *ADVISORIES]:
            existing = await session.scalar(
                select(ContentItem.id).where(ContentItem.slug == spec["slug"])
            )
            if existing is not None:
                skipped += 1
                print(f"  exists: {spec['slug']}")  # noqa: T201
                continue
            await create_item(session, published_at=DRAFTED, states=[], **spec)
            created += 1
            print(f"  created (pending): {spec['slug']}")  # noqa: T201
        await session.commit()

    print(  # noqa: T201
        f"content packs: {created} created, {skipped} already present.\n"
        "ALL land PENDING — they are livestock/advisory copy drafted by an agent,\n"
        "and a human has to read them before any farmer does."
    )
    return 0


if __name__ == "__main__":
    configure_logging(get_settings().log_level)
    sys.exit(asyncio.run(main()))
