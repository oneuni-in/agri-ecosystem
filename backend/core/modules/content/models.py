"""Content Engine (E6) ORM models. Tables land in 0045.

The module rule this file is built around: **nothing auto-publishes.**
Every item — whether a human typed it or an RSS worker fetched it —
starts at `moderation_status = 'pending'` because it carries `UGCMixin`,
and only a human with the approver permission moves it forward. The
ingest worker has no code path that sets any other value, so a source
that starts publishing junk can at worst fill a moderation queue.

Attribution is stored per item, not per source, and it is NOT NULL for
anything that came from a feed: the display surface renders the source
name, the link back and the publisher's own `published_at`, so an item
whose provenance we lost has nowhere to render and must not exist.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, SoftDeleteMixin, TimestampMixin, UGCMixin, UUIDv7PKMixin

# ── content kinds ────────────────────────────────────────────────────
# `article` and `video` ship in A-U3 W1; `guide` and `advisory` in W2.
# One table, because they share every field that matters (i18n title,
# editorial state, tags) and differ only in which optional columns are
# populated — splitting them would duplicate the moderation gate four
# times, which is exactly the thing that must not be duplicated.
KIND_ARTICLE = "article"
KIND_VIDEO = "video"
KIND_GUIDE = "guide"
KIND_ADVISORY = "advisory"
KINDS = (KIND_ARTICLE, KIND_VIDEO, KIND_GUIDE, KIND_ADVISORY)

# ── approved video providers ─────────────────────────────────────────
# Deliberately in CODE, not in a table. This is the embed-origin
# allowlist — a security boundary — and a table is editable by anyone
# with admin write, which would turn "approved providers only" into
# "whatever an admin typed". Adding a provider is a code review.
#
# We store the provider key and the opaque video id, NEVER iframe HTML
# and never a full URL: the embed src is BUILT from this map at read
# time, so a crafted `video_id` cannot escape the origin it is pinned to.
VIDEO_PROVIDERS: dict[str, str] = {
    # youtube-nocookie: no cookie is set until the visitor presses play.
    "youtube": "https://www.youtube-nocookie.com/embed/{video_id}",
    "vimeo": "https://player.vimeo.com/video/{video_id}",
}

# Provider ids are opaque tokens from the provider, so the safe rule is a
# conservative character class rather than a per-provider parser.
VIDEO_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


def embed_url(provider: str, video_id: str) -> str | None:
    """The embeddable URL for an approved provider, or None.

    None is a real answer, not an error case: a row whose provider fell
    off the allowlist stops embedding rather than rendering a stale
    origin, and the card degrades to a link-out.
    """
    template = VIDEO_PROVIDERS.get(provider)
    return None if template is None else template.format(video_id=video_id)


class Source(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One curated feed we are allowed to ingest.

    The build prompt's "curated source list (config, not hardcoded)"
    lives here rather than in a Python constant so the list can be
    changed by migration/admin without a deploy — and so `terms_note`
    and `robots_checked_on` sit NEXT TO the feed URL. A source with no
    recorded terms check is a source nobody confirmed we may read.
    """

    __tablename__ = "sources"
    __table_args__ = {"schema": "content"}

    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # Rendered verbatim as the attribution line — the publisher's own name.
    name: Mapped[str] = mapped_column(Text, nullable=False)
    homepage_url: Mapped[str] = mapped_column(Text, nullable=False)
    feed_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # Why we believe we may ingest this feed, in words, e.g. "GoI public
    # domain (PIB terms of use)". Not decorative: it is the audit trail
    # behind the "APIs and licensed feeds only" rule.
    terms_note: Mapped[str] = mapped_column(Text, nullable=False)
    robots_checked_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Default tags stamped onto every item this source produces; an
    # editor can narrow them per item afterwards.
    verticals: Mapped[list[str]] = mapped_column(postgresql.JSONB, nullable=False)
    states: Mapped[list[str]] = mapped_column(postgresql.JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class ContentItem(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, UGCMixin, Base):
    """An article, video, guide or advisory.

    `moderation_status` comes from UGCMixin and defaults to `pending`.
    That default IS the no-auto-publish guarantee: the ingest worker
    never names the column, so there is no code path where a fetched
    item arrives approved.

    Slugs are immutable once assigned (ADR-0006) — the read path keys on
    them and they become indexed URLs.
    """

    __tablename__ = "items"
    __table_args__ = {"schema": "content"}

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    # i18n payloads: {"en": ..., "ta": ..., "hi": ...}. A locale may be
    # absent — the read path falls back to `en` rather than rendering a
    # blank, and a missing translation is visible as English text, not
    # as an empty card.
    title: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    # Long-form body, for guides written here. NULL for feed items: we
    # link out to the publisher rather than restating their article.
    body: Mapped[dict[str, Any] | None] = mapped_column(postgresql.JSONB, nullable=True)

    # ── attribution ──────────────────────────────────────────────────
    # NOT NULL and rendered: an item always says where it came from.
    # For first-party editorial rows that is agri.in itself.
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("content.sources.id"), nullable=True
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    # The PUBLISHER's timestamp, not ours. Feed order is unreliable, so
    # the feed UI sorts on this and shows it beside the source name.
    published_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    # The dedupe key (see ingest.normalise_url). UNIQUE, and NULL for
    # first-party items — Postgres allows many NULLs in a unique index,
    # which is the behaviour we want: hand-written rows never collide.
    canonical_url: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)

    # ── targeting ────────────────────────────────────────────────────
    verticals: Mapped[list[str]] = mapped_column(postgresql.JSONB, nullable=False)
    states: Mapped[list[str]] = mapped_column(postgresql.JSONB, nullable=False)
    # Primary language of the linked material. Distinct from the i18n
    # `title` map: a Tamil video keeps `language='ta'` even though its
    # card title is translated three ways.
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")

    # ── advisory targeting (kind='advisory'); 0046 ───────────────────
    # NULL/empty means UNRESTRICTED for all three. An article must not
    # have to populate targeting to stay visible, so absence is the
    # permissive default — but `list_advisories` never uses that default,
    # because an advisory with no window is a notice, not an alert.
    districts: Mapped[list[str] | None] = mapped_column(postgresql.JSONB, nullable=True)
    window_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    window_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    def live_on(self, day: date) -> bool:
        """Is this advisory's window open on `day`?"""
        if self.window_start and day < self.window_start:
            return False
        return not (self.window_end and day > self.window_end)

    def covers_district(self, district: str | None) -> bool:
        """Does this advisory target `district`? An empty target list means
        everywhere; a visitor with no known district only sees the
        everywhere ones, never a guess."""
        if not self.districts:
            return True
        return district is not None and district in self.districts

    # ── video (kind='video' only) ────────────────────────────────────
    video_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def embed(self) -> str | None:
        """Embed src for a video row; None for everything else."""
        if self.kind != KIND_VIDEO or not self.video_provider or not self.video_id:
            return None
        return embed_url(self.video_provider, self.video_id)


class Bookmark(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A reader's saved item.

    `user_id` carries no FK — modules never reach into identity's tables
    (the market_data.price_alerts precedent). The unique constraint makes
    saving twice a no-op rather than a duplicate, so the UI's toggle has
    no failure state to explain.
    """

    __tablename__ = "bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_bookmarks_user_id_item_id"),
        {"schema": "content"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("content.items.id"), nullable=False
    )


# Pull outcomes, mirroring market.ingest_runs (ADR-0012). Same reasoning:
# with no run row, "no new articles today" and "the worker never fired"
# leave an identical trace, and the second one is a silent outage.
OUTCOME_OK = "ok"
OUTCOME_EMPTY = "empty"
OUTCOME_FETCH_FAILED = "fetch_failed"
OUTCOME_WRITE_FAILED = "write_failed"
OUTCOME_DISABLED = "disabled"


class IngestRun(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One recorded ATTEMPT to read one source."""

    __tablename__ = "ingest_runs"
    __table_args__ = {"schema": "content"}

    source_slug: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    fetched: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    written: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Items already held under the same canonical URL. A high number here
    # is healthy — it means dedupe is working, not that the run failed.
    duplicates: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
