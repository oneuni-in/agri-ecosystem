"""Wire shapes for the content module (E6, A-U3 W1).

These are the frozen contract the `web-agri` feed renders from, mirrored
in `packages/types`. Two shapes carry the module's rules into the wire:

- `source_name` / `source_url` / `published_at` are NON-nullable on every
  card, so a surface literally cannot render an item without saying where
  it came from.
- `embed_url` is COMPUTED server-side from the provider allowlist and is
  never accepted as input. A client receives a URL it may frame; it never
  supplies one.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .models import KIND_VIDEO, VIDEO_ID_PATTERN, VIDEO_PROVIDERS, ContentItem

# Locale maps travel whole so the client picks with its own fallback rule,
# the same as market_data's TranslatedText.
Translated = dict[str, str]


class ContentCard(BaseModel):
    """One item as a feed card."""

    id: uuid.UUID
    kind: str
    slug: str
    title: Translated
    summary: Translated
    # ── attribution: all three required, all three rendered ──
    source_name: str
    source_url: str
    published_at: datetime
    canonical_url: str | None
    verticals: list[str]
    states: list[str]
    language: str
    # ── video-only, all None for other kinds ──
    duration_seconds: int | None = None
    video_provider: str | None = None
    embed_url: str | None = None
    bookmarked: bool = False


class ContentDetail(ContentCard):
    body: Translated | None = None


class ContentPage(BaseModel):
    items: list[ContentCard]
    next_cursor: str | None = None


class BookmarkIn(BaseModel):
    item_id: uuid.UUID


class ModerationIn(BaseModel):
    status: str = Field(pattern="^(approved|pending|rejected)$")


class ItemIn(BaseModel):
    """A first-party item written in the CMS.

    `moderation_status` is absent from this shape ON PURPOSE — it is not
    an omission to be fixed later. If the create call could name it, the
    human gate would be optional, and a compromised editor token could
    publish directly. New items always land `pending`.

    Video fields are validated here rather than in the handler so the
    rule travels with the contract: an approved provider key and an
    opaque id, never a URL and never iframe markup.
    """

    kind: str = Field(pattern="^(article|video|guide|advisory)$")
    slug: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9-]+$")
    title: Translated
    summary: Translated
    body: Translated | None = None
    source_name: str = Field(min_length=1, max_length=200)
    source_url: str = Field(min_length=1, max_length=2000)
    published_at: datetime
    verticals: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    language: str = Field(default="en", pattern="^(en|ta|hi)$")
    video_provider: str | None = None
    video_id: str | None = Field(default=None, pattern=VIDEO_ID_PATTERN)
    # Nullable: no keyless official API reports YouTube duration, and
    # scraping the watch page is out of bounds — so this is metadata the
    # human curator enters. A card with no duration renders without the
    # pill rather than showing an invented number.
    duration_seconds: int | None = Field(default=None, ge=1, le=86_400)

    @model_validator(mode="after")
    def _check_video(self) -> ItemIn:
        if self.kind == KIND_VIDEO:
            if not self.video_provider or not self.video_id:
                raise ValueError("kind='video' requires video_provider and video_id")
            if self.video_provider not in VIDEO_PROVIDERS:
                raise ValueError(
                    f"video_provider must be one of {', '.join(sorted(VIDEO_PROVIDERS))}"
                )
        elif self.video_provider or self.video_id or self.duration_seconds:
            raise ValueError("video fields are only valid on kind='video'")
        return self


class QueueCard(ContentCard):
    """A queue row additionally shows the state it is sitting in — the
    reader-facing card never does, because a reader only ever sees
    approved items."""

    moderation_status: str


class QueuePage(BaseModel):
    items: list[QueueCard]
    next_cursor: str | None = None


def to_card(item: ContentItem, *, bookmarked: bool = False) -> ContentCard:
    return ContentCard(
        id=item.id,
        kind=item.kind,
        slug=item.slug,
        title=dict(item.title),
        summary=dict(item.summary),
        source_name=item.source_name,
        source_url=item.source_url,
        published_at=item.published_at,
        canonical_url=item.canonical_url,
        verticals=list(item.verticals),
        states=list(item.states),
        language=item.language,
        # Video fields stay None on non-video kinds even if the columns
        # somehow hold values — the card must not sprout a duration.
        duration_seconds=item.duration_seconds if item.kind == KIND_VIDEO else None,
        video_provider=item.video_provider if item.kind == KIND_VIDEO else None,
        embed_url=item.embed(),
        bookmarked=bookmarked,
    )


def to_detail(item: ContentItem, *, bookmarked: bool = False) -> ContentDetail:
    return ContentDetail(
        **to_card(item, bookmarked=bookmarked).model_dump(),
        body=dict(item.body) if item.body else None,
    )


def to_queue_card(item: ContentItem) -> QueueCard:
    return QueueCard(**to_card(item).model_dump(), moderation_status=item.moderation_status)
