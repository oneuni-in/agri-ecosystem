"""A-U2 W3: three more honest Soon tiles — nurseries, poultry, fisheries.

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-16

Config only, per the "registry as data" rule: a vertical is a row plus a
landing page, never a build. The home grid and /categories render exactly
what this table returns, so these three appear — and their group counts
update — with no app-code change at all.

All three enter `soon: true`. Each has a real stage behind it (nurseries
is Stage B / D79; poultry and fisheries are post-launch backlog surfaces),
and a Soon tile that says so is the honest way to show a vertical we have
not built yet. Flipping one to live is a data edit once its surface ships.

Placement follows what a farmer would expect to find next to them:
nurseries sits with the other input suppliers, poultry and fisheries with
livestock under buy-sell.
"""

# -- THREAT/NOTES:
# - Data-only migration: 3 INSERTs into directory.vertical_registry, ON
#   CONFLICT DO NOTHING (idempotent, re-runnable, and it cannot clobber a
#   row an admin has since edited).
# - No DDL, no grants touched, no lock beyond three row inserts.
# - nav_placement carries presentation metadata only (group/order/icon/
#   soon) — no secrets, no PII, no executable content. Names are
#   first-party editorial TranslatedString content, not UGC, so there is
#   no moderation state to default to `pending`.
# - Nothing user-visible turns ON: every row is `soon: true`, which renders
#   a Soon tile and a self-noindexed landing (AG-A3), never a live surface
#   claiming inventory we do not have.
# - AG-A13 recorded "exactly 36 at A-U1" and stays true as history; the
#   grid assertion that matters going forward is AG-A2 (tile count EQUALS
#   registry count), which is why that spec reads the registry rather than
#   a literal. A new checklist row records this growth.
# - downgrade removes exactly these three slugs, nothing else.

import json
from collections.abc import Sequence

import sqlalchemy as sa
import uuid6

from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (slug, en, ta, hi, group, order, icon)
_VERTICALS: list[tuple[str, str, str, str, str, int, str]] = [
    # Inputs & equipment — Stage B (D79) sits beside seeds/fertilizers.
    ("nurseries", "Nurseries", "நாற்றங்கால்", "नर्सरी", "inputs", 12, "🌿"),
    # Buy · sell · work — next to livestock, which is where someone
    # looking for birds or fish would already be looking.
    ("poultry", "Poultry", "கோழி வளர்ப்பு", "मुर्गी पालन", "buy-sell", 7, "🐔"),
    ("fisheries", "Fisheries", "மீன் வளர்ப்பு", "मत्स्य पालन", "buy-sell", 8, "🐟"),
]

_INSERT = sa.text(
    "INSERT INTO directory.vertical_registry"
    " (id, slug, name, engines_enabled, nav_placement, status)"
    " VALUES (:id, :slug, CAST(:name AS jsonb), CAST(:engines AS jsonb),"
    " CAST(:nav AS jsonb), 'active')"
    " ON CONFLICT (slug) DO NOTHING"
)


def upgrade() -> None:
    conn = op.get_bind()
    for slug, en, ta, hi, group, order, icon in _VERTICALS:
        conn.execute(
            _INSERT,
            {
                "id": str(uuid6.uuid7()),
                "slug": slug,
                "name": json.dumps({"en": en, "ta": ta, "hi": hi}),
                # Engines arrive with each vertical's stage; the row
                # existing FIRST is the point.
                "engines": json.dumps({}),
                "nav": json.dumps(
                    {"agri_home": {"group": group, "order": order, "icon": icon, "soon": True}}
                ),
            },
        )


def downgrade() -> None:
    slugs = ", ".join(f"'{v[0]}'" for v in _VERTICALS)
    op.execute(f"DELETE FROM directory.vertical_registry WHERE slug IN ({slugs})")
