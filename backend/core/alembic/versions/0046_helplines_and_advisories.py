"""A-U3 W2: helplines become an E5 dataset; advisories get their targeting.

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-17

Two things, both about data that was previously hardcoded or missing:

  market.helplines  — the A-U1 deviation being paid off. Helplines shipped
                      as `apps/web-agri/data/helplines.ts`, a static TS
                      file, "pending E5 migration". This is that migration.
                      The static file is DELETED in the same commit, not
                      left as a dead fallback — a second copy of a phone
                      number is a second thing to keep true.

  content.items     — advisory targeting columns. A pest alert that shows
  (+3 columns)        everywhere, forever, is not an alert; it is noise
                      that teaches people to ignore the next one.

WHAT "VERIFIED" MEANS HERE, AND WHAT IT DOES NOT.

The build prompt asks that each number be verified against its official
source as part of this migration. That was attempted for all four on
2026-08-17. Exactly one could be confirmed from the primary source:

  1800-180-1551 (Kisan Call Centre) — CONFIRMED, twice: agriwelfare.gov.in
      (Dept. of Agriculture & Farmers Welfare) renders "Helpline Center
      1800-180-1551", and manage.gov.in/kcc carries the same number.
      Re-stamped verified_on = 2026-08-17 against agriwelfare.gov.in.

The other three could NOT be confirmed programmatically — pmkisan.gov.in
and dahd.gov.in render their contact blocks client-side or in images, and
the TN number lives in departmental PDFs. So they keep their ORIGINAL
A-U1 human verification date (2026-08-14) and their original source
domain. They are NOT restamped to today.

That rule is 0039's, verbatim: "nobody re-verified them today, and moving
data into a table is not verification." A `verified_on` of today on a
number nobody checked today is worse than no stamp at all, because the UI
renders the stamp and a reader would believe it. The three unconfirmed
numbers are flagged for the owner at CP2 — dialling them is the real
verification for a phone number anyway.
"""

# -- THREAT/NOTES:
# - One new table in the existing `market` schema; three nullable columns
#   added to content.items. No table rewrite: adding a NULLable column
#   with no default is a catalog-only change in PG16.
# - downgrade drops market.helplines and the three columns. Helpline rows
#   are reproducible from this file; advisory targeting on any advisory
#   written after this migration would be LOST — real data loss.
# - locks: CREATE TABLE + ADD COLUMN (nullable, no default) take catalog
#   locks only.
# - Public records, no PII: these are published government helpline
#   numbers, already printed on official sites.
# - Editorial/reference data written by migration and admins, never by
#   users, so there is no moderation state on helplines. The advisory
#   columns hang off content.items, which DOES carry the gate.
# - Explicit per-table GRANT to app_rt (0023/0027/0038/0045 precedent).
# - No new enum, no new role, no cross-schema FK.

import json
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, soft_delete_column, timestamp_columns

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The one number re-verified today, and the exact page it was read from.
_RECHECKED_ON = date(2026, 8, 17)
# The A-U1 human check these three carry forward unchanged.
_ORIGINAL_CHECK = date(2026, 8, 14)

# (slug, en, ta, hi, display_number, dial, scope, state, source, source_url,
#  verified_on, sort_order)
_HELPLINES: list[tuple[str, str, str, str, str, str, str, str | None, str, str, date, int]] = [
    (
        "kcc",
        "Kisan Call Centre",
        "விவசாயி அழைப்பு மையம்",
        "किसान कॉल सेंटर",
        "1800-180-1551",
        "18001801551",
        "national",
        None,
        "agriwelfare.gov.in",
        "https://agriwelfare.gov.in/",
        _RECHECKED_ON,
        1,
    ),
    (
        "tn-agri",
        "TN Agri Dept",
        "தமிழ்நாடு வேளாண்மைத் துறை",
        "तमिलनाडु कृषि विभाग",
        "1800-425-1556",
        "18004251556",
        "state",
        "Tamil Nadu",
        "tn.gov.in",
        "https://www.tn.gov.in/department/1",
        _ORIGINAL_CHECK,
        2,
    ),
    (
        "animal-husbandry",
        "Animal husbandry",
        "கால்நடை பராமரிப்பு",
        "पशुपालन",
        "1962",
        "1962",
        "national",
        None,
        "dahd.gov.in",
        "https://dahd.gov.in/",
        _ORIGINAL_CHECK,
        3,
    ),
    (
        "pm-kisan",
        "PM-Kisan help",
        "பிஎம்-கிசான் உதவி",
        "पीएम-किसान सहायता",
        "155261",
        "155261",
        "national",
        None,
        "pmkisan.gov.in",
        "https://pmkisan.gov.in/",
        _ORIGINAL_CHECK,
        4,
    ),
]


def upgrade() -> None:
    op.create_table(
        "helplines",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        # The display name is DATA now, not an i18n key. A helpline added
        # by an admin next month must render in three languages without a
        # deploy, which a message-catalog key cannot do.
        sa.Column("name", postgresql.JSONB, nullable=False),
        # Exactly as printed by the source, spacing and all.
        sa.Column("number", sa.Text, nullable=False),
        # Digits only, for tel:. Stored rather than derived because short
        # codes (1962, 155261) and toll-free numbers are dialled
        # differently and a strip-the-punctuation rule would be a guess.
        sa.Column("dial", sa.Text, nullable=False),
        # 'national' | 'state'. A state helpline is only offered to a
        # visitor in that state — showing a Tamil Nadu number to someone
        # in Bihar is worse than showing one fewer number.
        sa.Column("scope", sa.Text, nullable=False, server_default="national"),
        sa.Column("state", sa.Text, nullable=True),
        # Provenance, per number, rendered by the UI (the constitution's
        # source+date rule; market_data/CLAUDE.md forbids serving a
        # dataset without it).
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("verified_on", sa.Date, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        schema="market",
    )

    # ── advisory targeting (content.items) ───────────────────────────
    # All three NULLable, and NULL means "unrestricted" on purpose: the
    # columns exist for advisories, and an article must not have to
    # populate them to stay visible.
    op.add_column(
        "items",
        # Empty list / NULL = every district. A list = only these.
        sa.Column("districts", postgresql.JSONB, nullable=True),
        schema="content",
    )
    op.add_column(
        "items",
        # The window an advisory is TRUE for. Fall armyworm in maize is a
        # fact about a few weeks, not a permanent notice, and a stale
        # alert on screen is how people learn to scroll past alerts.
        sa.Column("window_start", sa.Date, nullable=True),
        schema="content",
    )
    op.add_column(
        "items",
        sa.Column("window_end", sa.Date, nullable=True),
        schema="content",
    )
    # The advisory read: approved advisories live on a given date.
    op.create_index(
        "ix_items_advisory_window",
        "items",
        ["kind", "window_start", "window_end"],
        schema="content",
        postgresql_where=sa.text("kind = 'advisory'"),
    )

    conn = op.get_bind()
    insert = sa.text(
        "INSERT INTO market.helplines"
        " (id, slug, name, number, dial, scope, state, source, source_url,"
        "  verified_on, sort_order)"
        " VALUES (:id, :slug, CAST(:name AS jsonb), :number, :dial, :scope, :state,"
        "  :source, :source_url, :verified_on, :sort_order)"
        " ON CONFLICT (slug) DO NOTHING"
    )
    for (
        slug,
        en,
        ta,
        hi,
        number,
        dial,
        scope,
        state,
        source,
        source_url,
        verified_on,
        sort_order,
    ) in _HELPLINES:
        conn.execute(
            insert,
            {
                "id": str(uuid6.uuid7()),
                "slug": slug,
                "name": json.dumps({"en": en, "ta": ta, "hi": hi}),
                "number": number,
                "dial": dial,
                "scope": scope,
                "state": state,
                "source": source,
                "source_url": source_url,
                "verified_on": verified_on,
                "sort_order": sort_order,
            },
        )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON market.helplines TO app_rt")


def downgrade() -> None:
    op.drop_index("ix_items_advisory_window", table_name="items", schema="content")
    op.drop_column("items", "window_end", schema="content")
    op.drop_column("items", "window_start", schema="content")
    op.drop_column("items", "districts", schema="content")
    op.drop_table("helplines", schema="market")
