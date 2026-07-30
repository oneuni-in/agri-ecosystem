# Milk.in / Agri i18n glossary (D27)

Canonical en → ta → hi renderings. New UI strings and seeded content MUST
use these; deviations are review findings. Sources: `packages/ui/src/i18n/messages/*.json`
catalogs, `backend/core/data/geo/*.csv` `name_ta` columns, milk spec-schema
field labels (`backend/core/alembic/versions/0018_catalog_v1.py`).

| en | ta | hi |
|---|---|---|
| milk | பால் | दूध |
| vendor | விற்பனையாளர் | विक्रेता |
| dairy | பால் பண்ணை நிறுவனம் | डेयरी |
| dairy farm | பால் பண்ணை | डेयरी फ़ार्म |
| veterinarian | கால்நடை மருத்துவர் | पशु चिकित्सक |
| cattle feed | கால்நடை தீவனம் | पशु आहार |
| cooperative | கூட்டுறவு சங்கம் | सहकारी समिति |
| brand | பிராண்ட் | ब्रांड |
| shop | கடை | दुकान |
| pincode | பின்கோடு | पिनकोड |
| delivery | டெலிவரி | डिलीवरी |
| fresh | புதிய | ताज़ा |
| cow milk | பசும்பால் | गाय का दूध |
| buffalo milk | எருமைப்பால் | भैंस का दूध |
| near you | உங்களருகில் | आपके पास |
| category | வகை | श्रेणी |
| product | பொருள் | उत्पाद |
| business | வணிகம் | व्यवसाय |
| verified | சரிபார்க்கப்பட்டது | सत्यापित |
| language | மொழி | भाषा |
| find | தேடு | खोजें |
| milk type | பால் வகை | दूध का प्रकार |
| fat % | கொழுப்பு % | वसा % |
| pack size | பேக் அளவு | पैक आकार |
| km away | கிமீ தொலைவில் | किमी दूर |
| ghee | நெய் | घी |
| paneer | பன்னீர் | पनीर |
| milk powder | பால் பொடி | दूध पाउडर |
| yogurt | யோகர்ட் | योगर्ट |
| lassi | லஸ்சி | लस्सी |
| curd | தயிர் | दही |
| buttermilk | மோர் | छाछ |
| cheese | சீஸ் | चीज़ |
| butter | வெண்ணெய் | मक्खन |
| cream | கிரீம் | क्रीम |
| khoa | கோவா | खोया |
| flavoured milk | சுவையூட்டப்பட்ட பால் | फ्लेवर्ड दूध |
| mixed milk | கலப்பு பால் | मिश्रित दूध |

## Notes

- `category`/`product`/`business`/`verified`/`find` are pluralized/inflected
  in context (e.g. `find` → "Find shops" = "கடைகளைத் தேடு" / "दुकानें खोजें")
  — the glossary gives the base rendering, not every inflection.
- `milk type`, `fat %`, `pack size` are taken verbatim from the milk
  spec-schema v1 field labels (`0018_catalog_v1.py`) — do not re-translate
  these elsewhere; reuse the exact strings.
- `data/geo/states.csv` and `districts.csv` carry a `name_ta` column for
  future Tamil place-name overrides; it is currently unpopulated for all
  rows, so no place names are sourced from it yet. Once populated, place
  names used in `categoryBrowse.heading` must come from that column rather
  than being re-translated ad hoc.
- Tamil/Hindi renderings above were cross-checked against shipped strings
  in `packages/ui/src/i18n/messages/{ta,hi}.json` (e.g. `ui.search.results.kindProduct`,
  `ui.search.results.kindBusiness`, `ui.badges.verified`, `ui.location.find`,
  `ui.auth.profile.visibilityKeys.language`) so this table codifies what is
  already shipped rather than contradicting it.
- The dairy product taxonomy (`ghee`, `paneer`, `curd`, …) is taken verbatim
  from the milk spec-schema v2 `category` field's `option_meta`
  (`0029_milk_schema_v2.py`) — that JSONB is the source of truth and this
  table mirrors it. Do not re-translate these strings in UI code: the
  frontend renders the schema's labels directly.
