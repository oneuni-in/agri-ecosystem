"""A-U2 W3: turn `agri_today` on by default.

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-16

THE FLIP. A-U1 shipped the home's Today sections behind this flag against
deterministic fixtures, with the flag OFF everywhere. A-U2 replaced every
fixture with a real source — Open-Meteo (W1), ingested Agmarknet rows
(W2), and the E5 scheme/calendar datasets (W3, 0039) — and deleted
market_data/fixtures.py. There is nothing left for the flag to hide.

The flag itself STAYS. It is now a kill switch rather than a build gate:
if a data source turns bad, flipping it off via /ops/flags 404s the
endpoint and every Today section leaves the home's DOM, which is the
degradation A-U1 designed and the e2e specs still assert.
"""

# -- THREAT/NOTES:
# - Single-row UPDATE on public.feature_flags. No DDL, no lock beyond that
#   row, instant on any table size.
# - This is the one migration in A-U2 that changes what the public sees, so
#   it is deliberately its own revision: reverting the flip is
#   `alembic downgrade 0039` (or a flag toggle in /ops), with no other
#   change riding along.
# - Fail-closed is preserved elsewhere: `agri_live_feed` stays OFF (0037),
#   because no real feed endpoint exists yet and D3 forbids fabricating one.
# - Serving real data is gated on the data actually being there. Every read
#   path degrades to an empty state rather than a placeholder: no ingested
#   prices -> an empty mandi block, no zone -> an empty calendar, upstream
#   weather down with a cold cache -> 503 and the whole block is absent.
#   So flipping this on with an unpopulated database shows less, never
#   something invented.
# - downgrade restores enabled=false, which is A-U1's shipped state.

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE public.feature_flags SET enabled = true,"
            " description = 'agri.in TODAY strip + weather/mandi/schemes/calendar."
            " A-U2 replaced every fixture with a real source; this is now a kill"
            " switch, not a build gate.'"
            " WHERE key = 'agri_today'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE public.feature_flags SET enabled = false,"
            " description = 'A-U1: agri.in TODAY strip + weather/mandi/schemes/calendar;"
            " stubs until A-U2 flips real workers on'"
            " WHERE key = 'agri_today'"
        )
    )
