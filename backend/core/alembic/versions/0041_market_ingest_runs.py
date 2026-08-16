"""A-U2 W2 follow-up: the ingest run ledger.

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-16

WHY THIS TABLE EXISTS (ADR-0012).
The Agmarknet daily resource serves only the live day, so a day not
captured is gone permanently — no later job can recover it. That makes
the absence of rows for a date ambiguous in a way that cannot be resolved
after the fact: it could mean the mandi published nothing (a Sunday), the
scheduled job never fired, or the fetch failed. Rows alone cannot tell
those apart, and guessing later is impossible.

market.ingest_runs records every ATTEMPT — including the ones that
fetched nothing and the ones that failed — so a gap in the price series
stays explainable forever.
"""

# -- THREAT/NOTES:
# - One new table in the existing `market` schema. No existing table is
#   altered, so nothing outside market_data can be affected.
# - CREATE TABLE/INDEX take catalog locks only; there are no rows to rewrite.
# - No PII: this records job outcomes and counts against a public government
#   feed. `error` holds an exception type and message from our own client,
#   never a request body or an API key (the key never appears in an
#   AgmarknetError message — see modules/market_data/agmarknet.py).
# - downgrade drops the ledger. Unlike price_rows this data is NOT
#   re-derivable by re-running anything: it is the record of what happened.
#   Dropping it re-opens exactly the ambiguity the table exists to close.
# - counts are plain INTEGER, not NUMERIC: they are cardinalities, not money.

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from shared.migrations import pk_column, soft_delete_column, timestamp_columns

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingest_runs",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("source", sa.Text, nullable=False, server_default="agmarknet"),
        sa.Column("source_resource", sa.Text, nullable=False, server_default=""),
        # The state filter the pull was scoped to, or NULL for a national walk.
        sa.Column("state_filter", sa.Text, nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        # 'ok' | 'empty' | 'fetch_failed' | 'write_failed' | 'no_api_key' | 'disabled'
        # 'empty' is NOT 'fetch_failed': a quiet Sunday is a successful run
        # that found nothing, and conflating the two is the ambiguity this
        # table exists to remove.
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("fetched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("written", sa.Integer, nullable=False, server_default="0"),
        sa.Column("quarantined", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped_uncurated", sa.Integer, nullable=False, server_default="0"),
        # The newest arrival_date the feed carried this run. Answers "did we
        # ever hold 16 Aug?" without scanning price_rows, and survives even
        # when every row was skipped as uncurated.
        sa.Column("newest_arrival_date", sa.Date, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        schema="market",
    )
    op.create_check_constraint(
        "ck_ingest_runs_outcome",
        "ingest_runs",
        "outcome IN ('ok','empty','fetch_failed','write_failed','no_api_key','disabled')",
        schema="market",
    )
    # The ops read: "what happened on the last N runs", newest first.
    op.create_index(
        "ix_ingest_runs_started",
        "ingest_runs",
        [sa.text("started_at DESC")],
        schema="market",
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON market.ingest_runs TO app_rt")


def downgrade() -> None:
    op.drop_table("ingest_runs", schema="market")
