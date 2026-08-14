"""A-U1: seed the 36 agri verticals + agri_today / agri_live_feed flags.

D4 (agri final plan): "registry is how verticals grow. 36 entries at A-U1
(farm-tools live, machinery-rental Soon)". The agri.in home/categories grid
renders FROM this registry — zero hardcoded category lists in app code.

Vertical model has no group/icon/soon columns (0018); per the U1 lesson of
extending data not schema, the agri grid metadata rides in nav_placement:

    nav_placement = {"agri_home": {"group": "...", "order": n,
                                   "icon": "…", "soon": bool}}

The 7 "Farm essentials" are live (their surfaces are home sections / tools);
everything else is an honest Soon tile until its stage (B/C/D/E) builds it.
Names are TranslatedString {en, ta, hi}; Tamil from A1 FINAL v4, Hindi
best-effort — flagged for review in the A-U1 PR.

Flags (D3 mechanism, fail-closed): agri_today and agri_live_feed enter OFF.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
import uuid6

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels = None
depends_on = None

# (slug, en, ta, hi, group, order, icon, soon)
_VERTICALS: list[tuple[str, str, str, str, str, int, str, bool]] = [
    # Farm essentials — live now
    ("mandi-prices", "Mandi prices", "சந்தை விலை", "मंडी भाव", "essentials", 1, "📈", False),
    ("weather", "Weather", "வானிலை", "मौसम", "essentials", 2, "🌦️", False),
    ("govt-schemes", "Govt schemes", "திட்டங்கள்", "सरकारी योजनाएं", "essentials", 3, "🏛️", False),
    ("agri-news", "Agri news", "செய்திகள்", "कृषि समाचार", "essentials", 4, "📰", False),
    ("knowledge", "Knowledge", "வழிகாட்டி", "जानकारी", "essentials", 5, "📚", False),
    ("helplines", "Helplines", "உதவி எண்", "हेल्पलाइन", "essentials", 6, "📞", False),
    ("farm-tools", "Farm tools", "கணிப்பான்கள்", "कृषि कैलकुलेटर", "essentials", 7, "🧮", False),
    # Inputs & equipment — Stage B
    ("seeds", "Seeds", "விதைகள்", "बीज", "inputs", 1, "🌱", True),
    ("fertilizers", "Fertilizers", "உரங்கள்", "उर्वरक", "inputs", 2, "🧪", True),
    ("crop-protection", "Crop protection", "பயிர் பாதுகாப்பு", "फसल सुरक्षा", "inputs", 3, "🛡️", True),
    ("tractors", "Tractors", "டிராக்டர்", "ट्रैक्टर", "inputs", 4, "🚜", True),
    ("implements", "Implements", "கருவிகள்", "कृषि औज़ार", "inputs", 5, "🔧", True),
    ("harvesters", "Harvesters", "அறுவடை", "हार्वेस्टर", "inputs", 6, "🌾", True),
    ("drip-irrigation", "Drip irrigation", "சொட்டு நீர்", "ड्रिप सिंचाई", "inputs", 7, "💧", True),
    ("pumps-solar", "Pumps & solar", "மோட்டார்", "पंप और सोलर", "inputs", 8, "☀️", True),
    ("agri-drones", "Agri drones", "ட்ரோன்", "कृषि ड्रोन", "inputs", 9, "🛸", True),
    ("machinery", "Machinery", "இயந்திரங்கள்", "मशीनरी", "inputs", 10, "⚙️", True),
    (
        "machinery-rental",
        "Machinery rental",
        "வாடகை · CHC",
        "मशीनरी किराया · CHC",
        "inputs",
        11,
        "🛠️",
        True,
    ),
    # Services & trust — Stage C
    ("soil-testing", "Soil testing", "மண் பரிசோதனை", "मिट्टी जांच", "services", 1, "🧫", True),
    ("water-testing", "Water testing", "நீர் பரிசோதனை", "पानी जांच", "services", 2, "🚰", True),
    ("agri-loans", "Agri loans", "கடன்", "कृषि ऋण", "services", 3, "🏦", True),
    ("crop-insurance", "Crop insurance", "காப்பீடு", "फसल बीमा", "services", 4, "☂️", True),
    ("warehouses", "Warehouses", "கிடங்கு", "गोदाम", "services", 5, "🏬", True),
    ("transport", "Transport", "போக்குவரத்து", "परिवहन", "services", 6, "🚛", True),
    ("vets-consulting", "Vets & consulting", "மருத்துவர்", "पशु चिकित्सक", "services", 7, "🩺", True),
    ("fpos", "FPOs", "உழவர் நிறுவனம்", "एफपीओ", "services", 8, "🤝", True),
    # Community & learning — Stage D
    ("forum-qa", "Forum & Q·A", "கலந்துரையாடல்", "मंच और सवाल-जवाब", "community", 1, "💬", True),
    ("events-webinars", "Webinars & events", "நிகழ்வுகள்", "कार्यक्रम", "community", 2, "🎪", True),
    ("blog", "Blog", "வலைப்பதிவு", "ब्लॉग", "community", 3, "✍️", True),
    ("experts", "Experts", "நிபுணர்கள்", "विशेषज्ञ", "community", 4, "🎓", True),
    # Buy · sell · work — Stage E
    ("livestock", "Livestock", "கால்நடை", "पशुधन", "buy-sell", 1, "🐄", True),
    ("land", "Land — sale & lease", "நிலம்", "ज़मीन", "buy-sell", 2, "🗺️", True),
    ("farm-labour", "Farm labour", "வேலை", "खेत मजदूरी", "buy-sell", 3, "👷", True),
    ("trade-leads", "Trade leads", "வர்த்தகம்", "व्यापार", "buy-sell", 4, "🌐", True),
    ("shops-repair", "Shops & repair", "கடைகள்", "दुकानें", "buy-sell", 5, "🏪", True),
    ("agritech-apps", "Agritech apps", "ஆப்ஸ்", "कृषि ऐप्स", "buy-sell", 6, "📱", True),
]

assert len(_VERTICALS) == 36, "D4 contract: exactly 36 agri verticals at A-U1"

_INSERT = sa.text(
    "INSERT INTO directory.vertical_registry"
    " (id, slug, name, engines_enabled, nav_placement, status)"
    " VALUES (:id, :slug, CAST(:name AS jsonb), CAST(:engines AS jsonb),"
    " CAST(:nav AS jsonb), 'active')"
    " ON CONFLICT (slug) DO NOTHING"
)


def upgrade() -> None:
    conn = op.get_bind()
    for slug, en, ta, hi, group, order, icon, soon in _VERTICALS:
        conn.execute(
            _INSERT,
            {
                "id": str(uuid6.uuid7()),
                "slug": slug,
                "name": json.dumps({"en": en, "ta": ta, "hi": hi}),
                # Engines arrive with each vertical's stage; the registry row
                # existing FIRST is the point (a vertical is a row + landing,
                # never a build).
                "engines": json.dumps({}),
                "nav": json.dumps(
                    {"agri_home": {"group": group, "order": order, "icon": icon, "soon": soon}}
                ),
            },
        )
    op.execute(
        sa.text(
            "INSERT INTO public.feature_flags (key, enabled, description) VALUES "
            "('agri_today', false, "
            "'A-U1: agri.in TODAY strip + weather/mandi/schemes/calendar sections; "
            "stubs until A-U2 flips real workers on'), "
            "('agri_live_feed', false, "
            "'A-U1: agri.in live activity feed; OFF until a real anonymised feed "
            "endpoint exists — never fabricate events') "
            "ON CONFLICT (key) DO NOTHING"
        )
    )


def downgrade() -> None:
    slugs = ", ".join(f"'{v[0]}'" for v in _VERTICALS)
    op.execute(f"DELETE FROM directory.vertical_registry WHERE slug IN ({slugs})")
    op.execute("DELETE FROM public.feature_flags WHERE key IN ('agri_today', 'agri_live_feed')")
