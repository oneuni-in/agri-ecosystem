"""A-U2 AG-A17: seed the Kharif 2026-27 MSP rows.

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-17

0039 created market.msp and left it EMPTY on purpose: an MSP is a number
a farmer may act on, so it must not enter the database without a primary
source and a date. This fills it, from the primary source.

SOURCE: "Cabinet approves Minimum Support Prices (MSP) for Kharif Crops
for Marketing Season 2026-27", Press Information Bureau, released
13 May 2026 —
https://www.pib.gov.in/PressReleasePage.aspx?PRID=2260618&reg=48&lang=2

Only two of the eight curated commodities are MSP crops. Paddy and
groundnut are in the mandated list; tomato, onion, banana, turmeric and
dry chilli are not, and coconut is not either (copra is the MSP
commodity, and copra is not what our `coconut` row tracks). Seeding an
MSP for any of those would be inventing a guarantee that does not exist.

Figures read off the release's own table, in rupees per quintal, with the
year-on-year deltas cross-checked against the same row:
  Paddy (Common)  2441   (2025-26: 2369, stated increase 72)   2441-2369=72 ✓
  Groundnut       7517   (2025-26: 7263, stated increase 254)  7517-7263=254 ✓

WHY THIS SEASON. Kharif Marketing Season 2026-27 is the season the crop
now in the ground will be sold into, so it is the number that matters to
someone reading a price card today.
"""

# -- THREAT/NOTES:
# - Two INSERTs into market.msp. No DDL, no other table touched, no lock
#   beyond two rows.
# - This is the one migration in A-U2 that publishes a GUARANTEED PRICE.
#   Both rows carry the primary-source URL and the date it was read, and
#   the UI renders that provenance, so a stale or wrong figure is
#   traceable rather than anonymous.
# - The numbers were transcribed from the PIB release by the agent, not by
#   a human, and the deltas were cross-checked arithmetically (above). The
#   owner should spot-check both against the linked release; that is a
#   30-second job and the URL is right here.
# - ON CONFLICT DO NOTHING on the (commodity_id, season) unique key: safe
#   to re-run, and it will not clobber a correction made by hand later.
# - Commodities absent from the mandated MSP list get NO row, so the
#   overlay stays absent on their cards rather than implying a floor price
#   that does not exist.
# - downgrade removes exactly these two rows.

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
import uuid6

from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEASON = "Kharif 2026-27"
SOURCE_URL = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2260618&reg=48&lang=2"
VERIFIED_ON = date(2026, 8, 17)

# (commodity slug, MSP in rupees per quintal)
_MSP: list[tuple[str, str]] = [
    ("paddy", "2441.00"),
    ("groundnut", "7517.00"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for slug, price in _MSP:
        conn.execute(
            sa.text(
                "INSERT INTO market.msp"
                " (id, commodity_id, season, price_qtl, verified_against, verified_on)"
                " SELECT :id, c.id, :season, CAST(:price AS numeric), :src, :on"
                " FROM market.commodities c WHERE c.slug = :slug"
                " ON CONFLICT (commodity_id, season) DO NOTHING"
            ),
            {
                "id": str(uuid6.uuid7()),
                "season": SEASON,
                "price": price,
                "src": SOURCE_URL,
                "on": VERIFIED_ON,
                "slug": slug,
            },
        )


def downgrade() -> None:
    op.execute(f"DELETE FROM market.msp WHERE season = '{SEASON}'")
