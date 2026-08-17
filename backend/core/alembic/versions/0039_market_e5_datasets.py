"""A-U2 W3: schemes, crop calendar and MSP as E5 datasets.

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-16

The last three blocks of the Today payload that were still A-U1 fixtures
become admin-managed rows, which is what this module is for ("E5:
admin-managed structured datasets ... rendered as browsable reference
sections"). Once these exist, market_data/fixtures.py is deleted and the
`agri_today` flag flips on.

  market.schemes          — scheme cards, each with the official domain
                            it was verified against and the date a human
                            checked it. The UI renders that stamp FROM
                            the row, so a stale entry is visibly stale.
  market.scheme_deadlines — the deadline chips. `due_on` is what makes a
                            deadline honest: a passed date stops being
                            served instead of advertising a window that
                            closed. Rolling obligations (the PMFBY 72-hour
                            crop-loss intimation) carry due_on = NULL and
                            never expire.
  market.crop_calendars   — one row per agro-climatic zone, holding the
                            in-season months and the sowing/harvesting
                            windows. The month strip itself is COMPUTED at
                            read time from the current date; storing it
                            would go stale the moment the month turned.
  market.msp              — current-season minimum support prices, keyed
                            to a curated commodity. SEEDED EMPTY on
                            purpose: every row needs a human check against
                            CACP/PIB, and an unverified MSP is worse than
                            no MSP. The overlay renders only where a row
                            exists, so empty means no overlay.

The seeded scheme/calendar content carries over from the A-U1 fixture,
which was reviewed in that PR, WITH ITS ORIGINAL verified_on DATES. They
are not restamped to today: nobody re-verified them today, and moving
data into a table is not verification.
"""

# -- THREAT/NOTES:
# - New tables only, in the existing `market` schema; no existing table is
#   altered and no other module's data is touched.
# - downgrade drops the four tables and their rows. That content is
#   first-party editorial seed data reproducible by re-running this
#   migration, so the loss is recoverable — but it is real data loss.
# - locks: CREATE TABLE/INDEX take catalog locks only; no table rewrite.
# - Editorial content, not UGC: these rows are written by admins/migrations,
#   never by users, so there is no moderation state to default to `pending`.
# - No PII. Scheme rows carry public URLs on official domains only; the
#   AG-A11 link checker enforces the domain allowlist for the sarkari hub
#   and the same rule applies to anything added here by hand.
# - `msp` is intentionally seeded with ZERO rows: MSP is a number farmers
#   may act on, so it must not enter the database unverified. The table
#   exists so the overlay code path is real and testable.
# - price/MSP columns are NUMERIC, never float (0038 precedent).

import json
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, soft_delete_column, timestamp_columns

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _t(en: str, ta: str, hi: str) -> str:
    return json.dumps({"en": en, "ta": ta, "hi": hi})


# (level, state_label|None, title, body, verified_against, verified_on, url, link_label, order)
_SCHEMES: list[tuple[str, str | None, str, str, str, str, str, str, int]] = [
    (
        "central",
        None,
        _t("PM-Kisan Samman Nidhi", "பிஎம்-கிசான்", "पीएम-किसान सम्मान निधि"),
        _t(
            "₹6,000/year in three instalments, direct to bank. 18th instalment being credited now.",
            "ஆண்டுக்கு ₹6,000 மூன்று தவணைகளில். 18வது தவணை வரவு வைக்கப்படுகிறது.",
            "₹6,000/वर्ष तीन किस्तों में, सीधे बैंक में। 18वीं किस्त जारी।",
        ),
        "pmkisan.gov.in",
        "2026-08-12",
        "https://pmkisan.gov.in/",
        _t("Check status & guide", "நிலை அறிக", "स्थिति देखें"),
        1,
    ),
    (
        "central",
        None,
        _t("PMFBY crop insurance", "PMFBY பயிர் காப்பீடு", "PMFBY फसल बीमा"),
        _t(
            "Kharif 2026 enrolment window open till 31 Aug. Premium: 2% for food crops.",
            "காரீஃப் 2026 பதிவு ஆக 31 வரை. உணவுப் பயிர்களுக்கு 2% பிரீமியம்.",
            "खरीफ 2026 नामांकन 31 अग तक। खाद्य फसलों के लिए 2% प्रीमियम।",
        ),
        "pmfby.gov.in",
        "2026-08-10",
        "https://pmfby.gov.in/",
        _t("Am I covered?", "காப்பீடு உள்ளதா?", "क्या मैं कवर हूं?"),
        2,
    ),
    (
        "state",
        _t("TN State", "தமிழ்நாடு", "तमिलनाडु"),
        _t("100% drip irrigation subsidy", "சொட்டு நீர் 100% மானியம்", "ड्रिप सिंचाई 100% सब्सिडी"),
        _t(
            "Small & marginal farmers, per-hectare cap. Apply via block agri office.",
            "சிறு விவசாயிகளுக்கு. வட்டார வேளாண் அலுவலகத்தில் விண்ணப்பிக்கவும்.",
            "छोटे किसानों के लिए। ब्लॉक कृषि कार्यालय से आवेदन करें।",
        ),
        "tnhorticulture.tn.gov.in",
        "2026-08-08",
        "https://tnhorticulture.tn.gov.in/",
        _t("Eligibility & documents", "தகுதி விவரம்", "पात्रता व दस्तावेज़"),
        3,
    ),
]

# (chip, title, note|None, due_on|None, order)
_DEADLINES: list[tuple[str, str, str | None, str | None, int]] = [
    (
        "20 AUG",
        _t("KCC saturation camp", "KCC முகாம்", "KCC शिविर"),
        _t("block offices", "வட்டார அலுவலகம்", "ब्लॉक कार्यालय"),
        "2026-08-20",
        1,
    ),
    (
        "31 AUG",
        _t("PMFBY Kharif enrolment closes", "PMFBY பதிவு முடிவு", "PMFBY नामांकन समाप्त"),
        None,
        "2026-08-31",
        2,
    ),
    (
        "15 SEP",
        _t("Drone subsidy", "ட்ரோன் மானியம்", "ड्रोन सब्सिडी"),
        _t("FPO applications", "FPO விண்ணப்பம்", "FPO आवेदन"),
        "2026-09-15",
        3,
    ),
    (
        # Rolling obligation, not a dated window: it applies whenever damage
        # happens, so it must never expire.
        "72 HRS",
        _t("PMFBY crop-loss intimation", "பயிர் சேத அறிவிப்பு", "फसल क्षति सूचना"),
        _t(
            "call 14447 within 72 hrs of damage",
            "சேதம் ஏற்பட்ட 72 மணி நேரத்தில் 14447",
            "क्षति के 72 घंटे में 14447",
        ),
        None,
        4,
    ),
]

_CALENDAR_ZONE = {
    "slug": "tn-west",
    "name": _t("TN west zone", "தமிழ்நாடு மேற்கு மண்டலம்", "तमिलनाडु पश्चिम क्षेत्र"),
    # Districts this zone covers; the read path matches the visitor's
    # district against this list.
    "districts": json.dumps(["Coimbatore", "Tiruppur", "Erode", "Salem", "Namakkal", "Karur"]),
    # Kharif/samba season months (1-12) for the strip's in-season shading.
    "in_season_months": json.dumps([7, 8, 9, 10]),
    "sowing": json.dumps(
        [
            {
                "icon": "🌾",
                "label": {"en": "Samba paddy", "ta": "சம்பா நெல்", "hi": "सांबा धान"},
                "until": {"en": "till 25 Aug", "ta": "ஆக 25 வரை", "hi": "25 अग तक"},
            },
            {
                "icon": "🌽",
                "label": {"en": "Maize", "ta": "மக்காச்சோளம்", "hi": "मक्का"},
                "until": {"en": "till 30 Aug", "ta": "ஆக 30 வரை", "hi": "30 अग तक"},
            },
            {
                "icon": "🥜",
                "label": {"en": "Groundnut (rainfed)", "ta": "நிலக்கடலை", "hi": "मूंगफली"},
                "until": {"en": "till 20 Aug", "ta": "ஆக 20 வரை", "hi": "20 अग तक"},
            },
            {
                "icon": "🫘",
                "label": {"en": "Black gram", "ta": "உளுந்து", "hi": "उड़द"},
                "until": {"en": "till 5 Sep", "ta": "செப 5 வரை", "hi": "5 सित तक"},
            },
        ]
    ),
    "harvesting": json.dumps(
        [
            {
                "icon": "🧅",
                "label": {"en": "Kharif onion", "ta": "கார் வெங்காயம்", "hi": "खरीफ प्याज़"},
                "until": {"en": "early lots", "ta": "முன் அறுவடை", "hi": "शुरुआती"},
            },
            {
                "icon": "🍌",
                "label": {"en": "Banana", "ta": "வாழை", "hi": "केला"},
                "until": {"en": "year-round", "ta": "ஆண்டு முழுவதும்", "hi": "सालभर"},
            },
        ]
    ),
    "verified_against": "tnau.ac.in",
    "verified_on": "2026-08-15",
}


def upgrade() -> None:
    op.create_table(
        "schemes",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("level", sa.Text, nullable=False),  # central | state
        sa.Column("state_label", postgresql.JSONB, nullable=True),
        sa.Column("title", postgresql.JSONB, nullable=False),
        sa.Column("body", postgresql.JSONB, nullable=False),
        sa.Column("verified_against", sa.Text, nullable=False),
        sa.Column("verified_on", sa.Date, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("link_label", postgresql.JSONB, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        schema="market",
    )

    op.create_table(
        "scheme_deadlines",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("chip", sa.Text, nullable=False),
        sa.Column("title", postgresql.JSONB, nullable=False),
        sa.Column("note", postgresql.JSONB, nullable=True),
        # NULL = rolling obligation, never expires. A date = stop serving
        # it once it has passed.
        sa.Column("due_on", sa.Date, nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        schema="market",
    )

    op.create_table(
        "crop_calendars",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("zone_slug", sa.Text, nullable=False, unique=True),
        sa.Column("name", postgresql.JSONB, nullable=False),
        sa.Column("districts", postgresql.JSONB, nullable=False),
        sa.Column("in_season_months", postgresql.JSONB, nullable=False),
        sa.Column("sowing", postgresql.JSONB, nullable=False),
        sa.Column("harvesting", postgresql.JSONB, nullable=False),
        sa.Column("verified_against", sa.Text, nullable=False),
        sa.Column("verified_on", sa.Date, nullable=False),
        schema="market",
    )

    op.create_table(
        "msp",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column(
            "commodity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("market.commodities.id"),
            nullable=False,
        ),
        sa.Column("season", sa.Text, nullable=False),  # e.g. "Kharif 2026-27"
        sa.Column("price_qtl", sa.Numeric(12, 2), nullable=False),
        # Same honesty contract as schemes: an MSP without a source URL and
        # a human date does not get served.
        sa.Column("verified_against", sa.Text, nullable=False),
        sa.Column("verified_on", sa.Date, nullable=False),
        schema="market",
    )
    op.create_unique_constraint(
        "uq_msp_commodity_season", "msp", ["commodity_id", "season"], schema="market"
    )

    conn = op.get_bind()
    scheme_insert = sa.text(
        "INSERT INTO market.schemes"
        " (id, level, state_label, title, body, verified_against, verified_on,"
        "  url, link_label, sort_order)"
        " VALUES (:id, :level, CAST(:state_label AS jsonb), CAST(:title AS jsonb),"
        "  CAST(:body AS jsonb), :verified_against, :verified_on, :url,"
        "  CAST(:link_label AS jsonb), :sort_order)"
    )
    for level, state_label, title, body, against, on, url, link_label, order in _SCHEMES:
        conn.execute(
            scheme_insert,
            {
                "id": str(uuid6.uuid7()),
                "level": level,
                "state_label": state_label,
                "title": title,
                "body": body,
                "verified_against": against,
                "verified_on": date.fromisoformat(on),
                "url": url,
                "link_label": link_label,
                "sort_order": order,
            },
        )

    deadline_insert = sa.text(
        "INSERT INTO market.scheme_deadlines (id, chip, title, note, due_on, sort_order)"
        " VALUES (:id, :chip, CAST(:title AS jsonb), CAST(:note AS jsonb),"
        "  :due_on, :sort_order)"
    )
    for chip, title, note, due_on, order in _DEADLINES:
        conn.execute(
            deadline_insert,
            {
                "id": str(uuid6.uuid7()),
                "chip": chip,
                "title": title,
                "note": note,
                "due_on": date.fromisoformat(due_on) if due_on else None,
                "sort_order": order,
            },
        )

    conn.execute(
        sa.text(
            "INSERT INTO market.crop_calendars"
            " (id, zone_slug, name, districts, in_season_months, sowing, harvesting,"
            "  verified_against, verified_on)"
            " VALUES (:id, :slug, CAST(:name AS jsonb), CAST(:districts AS jsonb),"
            "  CAST(:months AS jsonb), CAST(:sowing AS jsonb), CAST(:harvesting AS jsonb),"
            "  :against, :on)"
        ),
        {
            "id": str(uuid6.uuid7()),
            "slug": _CALENDAR_ZONE["slug"],
            "name": _CALENDAR_ZONE["name"],
            "districts": _CALENDAR_ZONE["districts"],
            "months": _CALENDAR_ZONE["in_season_months"],
            "sowing": _CALENDAR_ZONE["sowing"],
            "harvesting": _CALENDAR_ZONE["harvesting"],
            "against": _CALENDAR_ZONE["verified_against"],
            "on": date.fromisoformat(_CALENDAR_ZONE["verified_on"]),
        },
    )

    # market.msp is deliberately left empty — see the THREAT/NOTES block.

    for table in ("schemes", "scheme_deadlines", "crop_calendars", "msp"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON market.{table} TO app_rt")


def downgrade() -> None:
    op.drop_table("msp", schema="market")
    op.drop_table("crop_calendars", schema="market")
    op.drop_table("scheme_deadlines", schema="market")
    op.drop_table("schemes", schema="market")
