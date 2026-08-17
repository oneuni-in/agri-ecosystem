"""A-U2 W2: mandi price tables + the curated commodity/market registries.

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-16

Three tables in the existing `market` schema (created in 0001):

  market.commodities — the curated set the home cards and commodity
    pages render. Curated, not open-ended: every row carries a
    TranslatedText name (en/ta/hi) and an emoji, which an auto-created
    row from an API string could not. `agmarknet_name` is the exact
    upstream spelling we match on.
  market.markets — mandis seen in the feed, created on ingest. These
    are place names from a government feed, not editorial content, so
    they are English-only by design.
  market.price_rows — one row per (commodity, market, date, variety,
    grade). Prices are stored EXACTLY as published: rupees per quintal.
    Conversion to the per-kg figure the cards show happens at read time,
    so the stored number always matches the source.

Quarantine (spec W2): a row that fails a quality check is stored with
status='quarantined' and a reason, never deleted and never rendered.
Ops can see it; the site cannot.
"""

# -- THREAT/NOTES:
# - New tables only, in a schema that already exists; no existing table is
#   touched, so nothing outside market_data can be affected by this change.
# - downgrade drops the three tables and their data. That data is a cache of
#   a public government feed and is re-ingestible by re-running the daily
#   pull, so the loss is recoverable — but it is real data loss, hence the
#   explicit note.
# - locks: CREATE TABLE/INDEX take catalog locks only; there are no rows to
#   rewrite and no existing table is altered.
# - The unique index on (commodity_id, market_id, arrival_date, variety,
#   grade) is what makes ingestion IDEMPOTENT: re-running a pull for a day
#   already ingested updates in place instead of duplicating. It is the
#   single most load-bearing constraint in this migration.
# - Explicit per-table GRANTs to app_rt (the 0023/0027 precedent), never a
#   blanket GRANT ON ALL TABLES: this schema will hold more later.
# - No PII: mandi prices and market names are public records. Nothing here
#   is user-generated, so there is no moderation state — `status` is a data
#   quality flag, not a UGC moderation flag.
# - price columns are NUMERIC, not float: money-shaped values must not carry
#   binary rounding error, matching billing's precedent.

import json
from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, soft_delete_column, timestamp_columns

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (slug, en, ta, hi, emoji, display_unit, agmarknet_name)
# The eight the A1 home renders. Names/emoji carry over from the A-U1
# fixture, which was reviewed against A1 FINAL v4; `agmarknet_name` is
# the upstream spelling, which is not always the obvious one
# ("Paddy(Common)" has no space, as published).
_COMMODITIES: list[tuple[str, str, str, str, str, str, str]] = [
    ("tomato", "Tomato", "தக்காளி", "टमाटर", "🍅", "kg", "Tomato"),
    ("onion", "Onion", "வெங்காயம்", "प्याज़", "🧅", "kg", "Onion"),
    ("paddy", "Paddy (common)", "நெல்", "धान", "🌾", "kg", "Paddy(Common)"),
    ("turmeric", "Turmeric", "மஞ்சள்", "हल्दी", "🟡", "kg", "Turmeric"),
    ("coconut", "Coconut", "தேங்காய்", "नारियल", "🥥", "kg", "Coconut"),
    ("banana", "Banana", "வாழை", "केला", "🍌", "kg", "Banana"),
    ("groundnut", "Groundnut", "நிலக்கடலை", "मूंगफली", "🥜", "kg", "Groundnut"),
    ("dry-chilli", "Dry chilli", "காய்ந்த மிளகாய்", "सूखी मिर्च", "🌶️", "kg", "Dry Chillies"),
]


def upgrade() -> None:
    op.create_table(
        "commodities",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("name", postgresql.JSONB, nullable=False),  # TranslatedText
        sa.Column("emoji", sa.Text, nullable=False, server_default=""),
        # What the CARD shows. Agmarknet publishes rupees per quintal for
        # everything; this is the unit we present after conversion.
        sa.Column("display_unit", sa.Text, nullable=False, server_default="kg"),
        # Exact upstream spelling. Unique so two curated rows cannot claim
        # the same feed commodity and silently split its history.
        sa.Column("agmarknet_name", sa.Text, nullable=False, unique=True),
        schema="market",
    )

    op.create_table(
        "markets",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("district", sa.Text, nullable=False),
        schema="market",
    )
    op.create_unique_constraint(
        "uq_markets_state_district_name",
        "markets",
        ["state", "district", "name"],
        schema="market",
    )

    op.create_table(
        "price_rows",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column(
            "commodity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("market.commodities.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "market_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("market.markets.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("arrival_date", sa.Date, nullable=False, index=True),
        sa.Column("variety", sa.Text, nullable=False, server_default=""),
        sa.Column("grade", sa.Text, nullable=False, server_default=""),
        # As published: rupees per quintal. Never pre-converted.
        sa.Column("min_price_qtl", sa.Numeric(12, 2), nullable=False),
        sa.Column("max_price_qtl", sa.Numeric(12, 2), nullable=False),
        sa.Column("modal_price_qtl", sa.Numeric(12, 2), nullable=False),
        # 'active' renders; 'quarantined' is visible to ops only.
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("quarantine_reason", sa.Text, nullable=True),
        # Provenance travels with every row (constitution: verified data
        # carries source + date).
        sa.Column("source", sa.Text, nullable=False, server_default="agmarknet"),
        sa.Column("source_resource", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "ingested_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="market",
    )
    # Idempotency + dedupe in one constraint: the daily pull re-runs safely
    # and a feed that repeats a row cannot double-count it.
    op.create_unique_constraint(
        "uq_price_rows_natural_key",
        "price_rows",
        ["commodity_id", "market_id", "arrival_date", "variety", "grade"],
        schema="market",
    )
    # The series read: "last N days for this commodity in this market",
    # newest first.
    op.create_index(
        "ix_price_rows_series",
        "price_rows",
        ["commodity_id", "market_id", sa.text("arrival_date DESC")],
        schema="market",
    )

    conn = op.get_bind()
    insert = sa.text(
        "INSERT INTO market.commodities"
        " (id, slug, name, emoji, display_unit, agmarknet_name)"
        " VALUES (:id, :slug, CAST(:name AS jsonb), :emoji, :unit, :agmarknet)"
        " ON CONFLICT (slug) DO NOTHING"
    )
    for slug, en, ta, hi, emoji, unit, agmarknet in _COMMODITIES:
        conn.execute(
            insert,
            {
                "id": str(uuid6.uuid7()),
                "slug": slug,
                "name": json.dumps({"en": en, "ta": ta, "hi": hi}),
                "emoji": emoji,
                "unit": unit,
                "agmarknet": agmarknet,
            },
        )

    for table in ("commodities", "markets", "price_rows"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON market.{table} TO app_rt")


def downgrade() -> None:
    op.drop_table("price_rows", schema="market")
    op.drop_table("markets", schema="market")
    op.drop_table("commodities", schema="market")
