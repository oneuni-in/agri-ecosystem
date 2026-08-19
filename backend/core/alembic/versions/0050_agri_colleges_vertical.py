"""Phase 2: the agri-colleges registry tile.

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-18

One row in `directory.vertical_registry`, so `/categories` and the home grid
render an agri-colleges tile that links to `/colleges`.

WHY A NEW MIGRATION RATHER THAN AN EDIT TO 0037.

0037 seeded the original 36 verticals and asserts `len(_VERTICALS) == 36` on
its own list. That assertion is correct and stays: 0037 really did add exactly
36, and rewriting an applied migration to make a later count true is how a
migration history stops describing what happened.

WHY IT LANDS `soon: false` IN ONE STEP.

The plan called for the tile to arrive `soon: true` and flip only once the
routes were green, on the reasoning that a live tile pointing at an unaudited
route puts a broken page on the home screen. That reasoning is about a tile
that ships BEFORE its routes. Here the nine routes, the Lighthouse gate and
this row are all in the same PR: if the gate fails the PR does not merge, so
the intermediate state never exists in dev. Two migrations to model a state
nobody can observe would be ceremony.

`name` carries EN/TA/HI. The Tamil and Hindi need owner review before merge —
the same review 0037 asked for, and it is listed in the PR body.
"""

# -- THREAT/NOTES:
# - One INSERT into directory.vertical_registry, ON CONFLICT DO NOTHING. No
#   schema change, no table rewrite, no lock beyond a row insert.
# - downgrade deletes the row by slug. The tile disappears; nothing else
#   references it, and no user data hangs off a registry row.
# - No PII: a vertical registry row is a name, an icon and a nav placement.
# - No new grant, no new enum, no new FK.

import json
from collections.abc import Sequence

import sqlalchemy as sa
import uuid6

from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SLUG = "agri-colleges"

# group/order place it after `experts` (community, 4) — the learning cluster,
# which is where a student looking for a college would look for it.
_NAV = {"agri_home": {"group": "community", "order": 5, "icon": "🏫", "soon": False}}
_NAME = {
    "en": "Agri colleges",
    # OWNER REVIEW before merge, as 0037 asked for its own strings.
    "ta": "வேளாண் கல்லூரிகள்",
    "hi": "कृषि महाविद्यालय",
}


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "INSERT INTO directory.vertical_registry"
            " (id, slug, name, engines_enabled, nav_placement, status)"
            " VALUES (:id, :slug, CAST(:name AS jsonb), CAST(:engines AS jsonb),"
            " CAST(:nav AS jsonb), 'active')"
            " ON CONFLICT (slug) DO NOTHING"
        ),
        {
            "id": str(uuid6.uuid7()),
            "slug": _SLUG,
            "name": json.dumps(_NAME),
            # The education engine is read-only and has no directory engine
            # behind it; the tile links straight to /colleges.
            "engines": json.dumps({}),
            "nav": json.dumps(_NAV),
        },
    )


def downgrade() -> None:
    op.execute(sa.text(f"DELETE FROM directory.vertical_registry WHERE slug = '{_SLUG}'"))
