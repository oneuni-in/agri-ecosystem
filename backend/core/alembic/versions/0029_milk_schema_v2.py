# backend/core/alembic/versions/0029_milk_schema_v2.py
"""M1: milk spec-schema v2 - the full dairy taxonomy as config. Adds a
required `category` enum carrying per-option i18n labels + icon keys,
demotes milk_type to optional (a ghee product has no milk type) and appends
the `mixed` option, then backfills every already-seeded milk product onto
v2 with category='milk'.

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-29

"""
# -- THREAT/NOTES:
# downgrade data loss: deletes the milk v2 schema row and reverts the
#   backfill (strips specs.category, re-pins schema_version to 1) for rows
#   whose category is exactly 'milk'. Products created AFTER this migration
#   in a non-milk category cannot be represented by v1 at all - downgrade
#   leaves them pinned at 2 with a now-absent schema, which renders as an
#   empty field list rather than an error (catalog_router.py:333 passes
#   `schema.fields if schema else []`). Accepted: forward-only in practice.
# locks: one INSERT into spec_schemas; one full UPDATE of
#   directory.products WHERE vertical_slug='milk' (~130 rows in the seeded
#   dev/staging DB, 0 in a fresh CI DB). Row-level locks for the duration of
#   a single small statement; no table rewrite, no index rebuild.
# rollout: spec_schemas is append-only BY GRANT (0018 revoked UPDATE/DELETE
#   from app_rt) - a taxonomy change is an INSERT of version N+1 and never
#   an edit. Options are APPEND-ONLY by contract: every v1 milk_type value
#   is repeated here, because products pinned at v1 still reference them and
#   validate_specs would reject a removed value on their next edit.
# schema-injection defence: fields JSONB below is validated by
#   modules/directory/specs.parse_fields on read AND is exercised by
#   tests/test_milk_schema_v2_migration.py, which round-trips it through
#   parse_fields and asserts full en/ta/hi coverage on every option.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

spec_schemas_table = sa.table(
    "spec_schemas",
    sa.column("id", _uuid),
    sa.column("vertical_slug", sa.Text),
    sa.column("version", sa.Integer),
    sa.column("fields", postgresql.JSONB),
    schema="directory",
)

# (value, en, ta, hi, icon_key) - the taxonomy. Adding a value later means
# publishing version N+1 with this list extended; no code changes anywhere.
DAIRY_TAXONOMY: list[tuple[str, str, str, str, str]] = [
    ("milk", "Milk", "பால்", "दूध", "milk"),
    ("ghee", "Ghee", "நெய்", "घी", "ghee"),
    ("paneer", "Paneer", "பன்னீர்", "पनीर", "paneer"),
    ("milk-powder", "Milk Powder", "பால் பொடி", "दूध पाउडर", "milk-powder"),
    ("yogurt", "Yogurt", "யோகர்ட்", "योगर्ट", "yogurt"),
    ("lassi", "Lassi", "லஸ்சி", "लस्सी", "lassi"),
    ("curd", "Curd", "தயிர்", "दही", "curd"),
    ("buttermilk", "Buttermilk", "மோர்", "छाछ", "buttermilk"),
    ("cheese", "Cheese", "சீஸ்", "चीज़", "cheese"),
    ("butter", "Butter", "வெண்ணெய்", "मक्खन", "butter"),
    ("cream", "Cream", "கிரீம்", "क्रीम", "cream"),
    ("khoa", "Khoa", "கோவா", "खोया", "khoa"),
    ("flavoured-milk", "Flavoured Milk", "சுவையூட்டப்பட்ட பால்", "फ्लेवर्ड दूध", "flavoured-milk"),
]

# APPEND-ONLY: the first five are v1's options, repeated verbatim.
MILK_TYPES: list[tuple[str, str, str, str]] = [
    ("cow", "Cow", "பசு", "गाय"),
    ("buffalo", "Buffalo", "எருமை", "भैंस"),
    ("a2", "A2", "A2", "A2"),
    ("toned", "Toned", "டோன்ட்", "टोन्ड"),
    ("organic", "Organic", "ஆர்கானிக்", "ऑर्गेनिक"),
    ("mixed", "Mixed", "கலப்பு பால்", "मिश्रित दूध"),
]


def _option_meta(rows: Sequence[tuple[str, ...]]) -> dict[str, dict[str, object]]:
    return {
        row[0]: {
            "label": {"en": row[1], "ta": row[2], "hi": row[3]},
            "icon": row[4] if len(row) > 4 else row[0],
        }
        for row in rows
    }


MILK_SCHEMA_V2_FIELDS: list[dict[str, object]] = [
    {
        "key": "category",
        "label": {"en": "Category", "ta": "வகை", "hi": "श्रेणी"},
        "type": "enum",
        "options": [row[0] for row in DAIRY_TAXONOMY],
        "option_meta": _option_meta(DAIRY_TAXONOMY),
        "required": True,
        "filterable": True,
        "facet": True,
        "group": "basics",
    },
    {
        "key": "milk_type",
        "label": {"en": "Milk type", "ta": "பால் வகை", "hi": "दूध का प्रकार"},
        "type": "enum",
        "options": [row[0] for row in MILK_TYPES],
        "option_meta": _option_meta(MILK_TYPES),
        # NOT required in v2: only the `milk` category has a milk type. The
        # seed normalizer enforces "milk category => milk_type present";
        # no runtime guard, because that would hardcode the taxonomy.
        "required": False,
        "filterable": True,
        "facet": True,
        "group": "basics",
    },
    {
        "key": "fat_percent",
        "label": {"en": "Fat %", "ta": "கொழுப்பு %", "hi": "वसा %"},
        "type": "number",
        "unit": "%",
        "min": 0,
        "max": 15,
        "filterable": True,
        "comparable": True,
        "group": "nutrition",
    },
    {
        "key": "pack_size",
        "label": {"en": "Pack size", "ta": "பேக் அளவு", "hi": "पैक आकार"},
        "type": "enum",
        "options": ["250ml", "500ml", "1l", "5l", "bulk"],
        "filterable": True,
        "facet": True,
        "group": "basics",
    },
]


def upgrade() -> None:
    op.bulk_insert(
        spec_schemas_table,
        [
            {
                "id": uuid6.uuid7(),
                "vertical_slug": "milk",
                "version": 2,
                "fields": MILK_SCHEMA_V2_FIELDS,
            }
        ],
    )
    # Backfill. Soft-deleted rows are included deliberately: an undeleted
    # product must not come back holding specs that fail its pinned schema.
    op.execute(
        """
        UPDATE directory.products
           SET specs = specs || '{"category": "milk"}'::jsonb,
               schema_version = 2
         WHERE vertical_slug = 'milk'
           AND specs->>'category' IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE directory.products
           SET specs = specs - 'category',
               schema_version = 1
         WHERE vertical_slug = 'milk'
           AND specs->>'category' = 'milk'
        """
    )
    op.execute("DELETE FROM directory.spec_schemas WHERE vertical_slug = 'milk' AND version = 2")
