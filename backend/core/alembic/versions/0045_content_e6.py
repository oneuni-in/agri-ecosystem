"""A-U3 W1: the content engine (E6) — news, video, and the curation gate.

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-17

The `content` schema has existed empty since 0001. This fills it:

  content.sources     — the curated feed list. The build prompt calls for
                        "config, not hardcoded", and a table is the config:
                        the list changes by migration or admin write, not
                        by deploy, and `terms_note` + `robots_checked_on`
                        sit next to the feed URL so nobody can add a
                        source without recording why we may read it.
  content.items       — one table for article/video/guide/advisory. They
                        share the i18n fields, the tags and — crucially —
                        the moderation gate. Four tables would mean four
                        copies of the gate, which is the one thing that
                        must exist exactly once.
  content.bookmarks   — a reader's shelf. user_id carries no FK; modules
                        never reach into identity (market.price_alerts
                        precedent).
  content.ingest_runs — one row per ATTEMPT, ADR-0012. Without it, "no
                        agriculture news today" and "the worker died three
                        weeks ago" leave the same trace: none.

NOTHING AUTO-PUBLISHES. `items.moderation_status` uses the shared
`pending` default and the ingest worker never names the column, so there
is no code path — and after this migration no schema default — by which
a fetched article can arrive already visible.

Seeded sources, and why each one is here:

  icar          ICAR (Indian Council of Agricultural Research), Government
                of India. Public-sector research body; GoI content is
                published for reuse with attribution.
  the-hindu     The Hindu, Agriculture section. A publicly offered RSS
                feed is an invitation to syndicate headline + link with
                attribution, which is exactly and only what we store: we
                never restate the article body (items.body stays NULL for
                feed rows) and every card links back.
  bl-agri       BusinessLine (The Hindu group), Agri-business.

robots.txt for all three was fetched on 2026-08-17 and none disallows the
feed path used here (`robots_checked_on` records that check).

DELIBERATELY EXCLUDED: pib.gov.in. Its RSS endpoint answers 403 to a
declared bot User-Agent. A 403 is the publisher saying no, and the fix
would be to disguise the client — so PIB stays out until there is an
authorised route in. This note exists so the next person does not
"discover" the workaround.
"""

# -- THREAT/NOTES:
# - New tables only, in the `content` schema created by 0001. No existing
#   table is altered; no other module's data is touched.
# - downgrade drops the four tables and their rows. Ingested news is
#   re-fetchable and the seed rows are reproducible from this file, but
#   editorial approvals and reader bookmarks are NOT — real data loss.
# - locks: CREATE TABLE/INDEX take catalog locks only; no table rewrite.
# - items is the ONE table here carrying the shared `moderation_status`
#   enum (ugc_column), default `pending`. That default is the
#   no-auto-publish guarantee at the schema level.
# - PII: content.bookmarks holds a user_id and nothing else — no name, no
#   contact. items/sources hold public editorial data only.
# - canonical_url is UNIQUE and NULLABLE: the dedupe key for feed rows,
#   and Postgres permits many NULLs, so hand-written items never collide.
# - Explicit per-table GRANTs to app_rt (the 0023/0027/0038 precedent),
#   never a blanket GRANT ON ALL TABLES — this schema will hold more.
# - No new role, no new enum, no cross-schema FK.

import json
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, soft_delete_column, timestamp_columns, ugc_column

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROBOTS_CHECKED_ON = date(2026, 8, 17)

# (slug, name, homepage_url, feed_url, terms_note, verticals, states)
_SOURCES: list[tuple[str, str, str, str, str, list[str], list[str]]] = [
    (
        "icar",
        "ICAR",
        "https://icar.org.in/",
        "https://icar.org.in/en/rss.xml",
        "Government of India (ICAR) public research communications; reused"
        " with attribution and a link back. robots.txt allows /en/rss.xml.",
        ["agri-news", "research"],
        [],
    ),
    (
        "the-hindu",
        "The Hindu",
        "https://www.thehindu.com/sci-tech/agriculture/",
        "https://www.thehindu.com/sci-tech/agriculture/feeder/default.rss",
        "Publisher-offered RSS: headline, summary and link only, always"
        " attributed, article body never restated. robots.txt allows the"
        " feeder path.",
        ["agri-news"],
        [],
    ),
    (
        "bl-agri",
        "BusinessLine",
        "https://www.thehindubusinessline.com/economy/agri-business/",
        "https://www.thehindubusinessline.com/economy/agri-business/feeder/default.rss",
        "Publisher-offered RSS: headline, summary and link only, always"
        " attributed, article body never restated. robots.txt allows the"
        " feeder path.",
        ["agri-news", "market"],
        [],
    ),
]


def upgrade() -> None:
    op.create_table(
        "sources",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        # Rendered verbatim as the attribution line.
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("homepage_url", sa.Text, nullable=False),
        sa.Column("feed_url", sa.Text, nullable=False, unique=True),
        # Why we believe we may ingest this feed, in words. NOT NULL so a
        # source cannot be added without answering the question.
        sa.Column("terms_note", sa.Text, nullable=False),
        sa.Column("robots_checked_on", sa.Date, nullable=True),
        sa.Column("verticals", postgresql.JSONB, nullable=False),
        sa.Column("states", postgresql.JSONB, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        schema="content",
    )

    op.create_table(
        "items",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        # THE GATE. Defaults to 'pending' — see the module note above.
        ugc_column(),
        sa.Column("kind", sa.Text, nullable=False),
        # Immutable once assigned (ADR-0006); becomes an indexed URL.
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("title", postgresql.JSONB, nullable=False),
        sa.Column("summary", postgresql.JSONB, nullable=False),
        # NULL for feed rows: we link out rather than republish.
        sa.Column("body", postgresql.JSONB, nullable=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content.sources.id"),
            nullable=True,
            index=True,
        ),
        # Attribution, NOT NULL: a card that cannot say where it came
        # from has nothing honest to render.
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        # The PUBLISHER's timestamp, not ours.
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=False),
        # Dedupe key, normalised by ingest.normalise_url before storage.
        sa.Column("canonical_url", sa.Text, nullable=True, unique=True),
        sa.Column("verticals", postgresql.JSONB, nullable=False),
        sa.Column("states", postgresql.JSONB, nullable=False),
        sa.Column("language", sa.Text, nullable=False, server_default="en"),
        # Video only. Provider is a KEY into the code-side allowlist, and
        # video_id is opaque — the embed src is built at read time, so no
        # row can carry an arbitrary iframe origin.
        sa.Column("video_provider", sa.Text, nullable=True),
        sa.Column("video_id", sa.Text, nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        schema="content",
    )
    # A video row must be complete or not a video: half-populated rows
    # would render a play button over nothing.
    op.create_check_constraint(
        "ck_items_video_fields_complete",
        "items",
        "kind <> 'video' OR (video_provider IS NOT NULL AND video_id IS NOT NULL)",
        schema="content",
    )
    # The feed read: approved items of a kind, newest published first.
    op.create_index(
        "ix_items_feed",
        "items",
        ["moderation_status", "kind", sa.text("published_at DESC")],
        schema="content",
    )
    # Tag filters run as JSONB containment, which needs GIN to not scan.
    op.create_index(
        "ix_items_verticals",
        "items",
        ["verticals"],
        postgresql_using="gin",
        schema="content",
    )

    op.create_table(
        "bookmarks",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        # No FK: modules never reach into identity's tables.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content.items.id"),
            nullable=False,
            index=True,
        ),
        schema="content",
    )
    # Makes saving twice a no-op instead of a duplicate — the UI toggle
    # has no "already saved" state to explain.
    op.create_unique_constraint(
        "uq_bookmarks_user_id_item_id", "bookmarks", ["user_id", "item_id"], schema="content"
    )

    op.create_table(
        "ingest_runs",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("source_slug", sa.Text, nullable=False, index=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("fetched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("written", sa.Integer, nullable=False, server_default="0"),
        # A high duplicate count is HEALTH, not failure: it means dedupe
        # is doing its job on a feed we already read today.
        sa.Column("duplicates", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "ingested_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="content",
    )

    conn = op.get_bind()
    insert = sa.text(
        "INSERT INTO content.sources"
        " (id, slug, name, homepage_url, feed_url, terms_note, robots_checked_on,"
        "  verticals, states)"
        " VALUES (:id, :slug, :name, :homepage, :feed, :terms, :robots,"
        "  CAST(:verticals AS jsonb), CAST(:states AS jsonb))"
        " ON CONFLICT (slug) DO NOTHING"
    )
    for slug, name, homepage, feed, terms, verticals, states in _SOURCES:
        conn.execute(
            insert,
            {
                "id": str(uuid6.uuid7()),
                "slug": slug,
                "name": name,
                "homepage": homepage,
                "feed": feed,
                "terms": terms,
                "robots": _ROBOTS_CHECKED_ON,
                "verticals": json.dumps(verticals),
                "states": json.dumps(states),
            },
        )

    for table in ("sources", "items", "bookmarks", "ingest_runs"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON content.{table} TO app_rt")


def downgrade() -> None:
    op.drop_table("ingest_runs", schema="content")
    op.drop_table("bookmarks", schema="content")
    op.drop_table("items", schema="content")
    op.drop_table("sources", schema="content")
