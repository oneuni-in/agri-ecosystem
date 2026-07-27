"""D27: dairy service categories (veterinarian, feed-supplier, dairy-farm,
cooperative) - pure config on the D15 directory engine, no new tables.

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-25

"""
# -- THREAT/NOTES:
# downgrade data loss: deletes exactly these four category rows by slug; if
#   any business has already been assigned one (business_categories FK), the
#   FK constraint blocks the delete rather than silently orphaning links -
#   acceptable, matches 0016's stance of leaving cleanup to an incident call.
# locks: four-row INSERT into an existing table; negligible.
# rollout: pure config seed, no app code depends on these rows existing until
#   this migration lands - CATEGORY_SITES/CATEGORY_SLUGS changes in this same
#   PR are additive and inert without the rows.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

# (slug, {en,ta,hi}, sort_order) - after 0016's set, which ends at 80.
DAIRY_CATEGORIES = [
    (
        "veterinarian",
        {"en": "Veterinarians", "ta": "கால்நடை மருத்துவர்கள்", "hi": "पशु चिकित्सक"},
        90,
    ),
    (
        "feed-supplier",
        {"en": "Cattle Feed Suppliers", "ta": "கால்நடை தீவனக் கடைகள்", "hi": "पशु आहार विक्रेता"},
        100,
    ),
    ("dairy-farm", {"en": "Dairy Farms", "ta": "பால் பண்ணைகள்", "hi": "डेयरी फ़ार्म"}, 110),
    (
        "cooperative",
        {"en": "Milk Cooperatives", "ta": "பால் கூட்டுறவு சங்கங்கள்", "hi": "दुग्ध सहकारी समितियाँ"},
        120,
    ),
]


def upgrade() -> None:
    op.bulk_insert(
        sa.table(
            "categories",
            sa.column("id", _uuid),
            sa.column("slug", sa.Text),
            sa.column("name", postgresql.JSONB),
            sa.column("sort_order", sa.Integer),
            schema="directory",
        ),
        [
            {"id": uuid6.uuid7(), "slug": slug, "name": name, "sort_order": order}
            for (slug, name, order) in DAIRY_CATEGORIES
        ],
    )


def downgrade() -> None:
    slugs = ", ".join(f"'{slug}'" for (slug, _, _) in DAIRY_CATEGORIES)
    op.execute(f"DELETE FROM directory.categories WHERE slug IN ({slugs})")
