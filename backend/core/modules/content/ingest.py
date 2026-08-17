"""RSS/Atom ingest for the content module (A-U3 W1).

Three rules shape this file:

1. **Nothing auto-publishes.** `insert_item` never names
   `moderation_status`, so every fetched row takes UGCMixin's `pending`
   default. There is no flag, no source setting and no argument that can
   make the worker publish. Approving is a human action in the CMS.

2. **Attribution survives the trip.** An entry with no title, no link or
   no publisher timestamp is SKIPPED, not defaulted: the card renders the
   source name, the link and the publisher's date, so an item missing any
   of them has nothing honest to display.

3. **Dedupe on the canonical URL**, normalised first — feeds re-publish
   the same story with campaign parameters attached, and a raw-string
   comparison would treat each one as new.

Feeds are untrusted XML from the public internet, so parsing goes
through defusedxml and the body is size-capped before it is parsed.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit

import httpx
from defusedxml import ElementTree as DefusedET
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    KIND_ARTICLE,
    OUTCOME_DISABLED,
    OUTCOME_EMPTY,
    OUTCOME_FETCH_FAILED,
    OUTCOME_OK,
    OUTCOME_WRITE_FAILED,
    ContentItem,
    IngestRun,
    Source,
)

log = logging.getLogger(__name__)

# A feed that will not answer in 20s is down as far as a nightly job is
# concerned; retrying is the next run's problem.
FETCH_TIMEOUT_SECONDS = 20.0

# Hard cap on the downloaded body. Guards the parser against a feed that
# suddenly serves something enormous, and bounds memory on a job that
# runs unattended.
MAX_FEED_BYTES = 5 * 1024 * 1024

# Government portals reject or blackhole unknown clients (the data.gov.in
# lesson in market_data/CLAUDE.md), and a feed publisher is entitled to
# know who is reading them.
USER_AGENT = "agri.in-content-bot/1.0 (+https://agri.in/about; contact@agri.in)"

# Tracking parameters feeds attach to the same story. Stripped before the
# URL becomes the dedupe key.
TRACKING_PARAM_PREFIXES = ("utm_", "pk_", "mc_", "ns_")
TRACKING_PARAMS = frozenset({"fbclid", "gclid", "igshid", "ref", "source", "amp"})

# Atom/RSS namespaces. RSS 2.0 is namespace-free; Atom is not; RDF/RSS 1.0
# puts items in the RDF namespace.
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rss1": "http://purl.org/rss/1.0/",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class FeedEntry:
    """One entry, already reduced to the fields a card needs."""

    title: str
    summary: str
    url: str
    published_at: datetime


@dataclass(frozen=True)
class IngestResult:
    outcome: str
    fetched: int = 0
    written: int = 0
    duplicates: int = 0
    skipped: int = 0
    error: str | None = None


def normalise_url(url: str) -> str:
    """The dedupe key for a story.

    Lowercases scheme+host, drops the fragment and every tracking
    parameter, and strips a trailing slash. Two feeds carrying the same
    article with different campaign tags collapse to one key; genuinely
    different paths stay different.
    """
    parts = urlsplit(url.strip())
    query = "&".join(
        pair
        for pair in parts.query.split("&")
        if pair
        and (key := pair.split("=", 1)[0].lower()) not in TRACKING_PARAMS
        and not key.startswith(TRACKING_PARAM_PREFIXES)
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def strip_html(raw: str) -> str:
    """Feed summaries are HTML. We render them as TEXT, never as markup —
    which removes the whole injection question rather than sanitising it."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", raw)).strip()


def slugify(title: str, published_at: datetime) -> str:
    """A stable, immutable slug (ADR-0006).

    Date-prefixed because two publishers legitimately title the same
    announcement identically, and because a dated URL reads honestly for
    news. Unicode titles (Tamil/Hindi headlines) reduce to their ASCII
    transliterable part; when nothing survives, the date plus a hash of
    the title keeps the slug non-empty and deterministic.
    """
    ascii_title = (
        unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii").lower()
    )
    stem = _SLUG_STRIP_RE.sub("-", ascii_title).strip("-")[:60].strip("-")
    if not stem:
        stem = f"item-{abs(hash(title)) % 10**8:08d}"
    return f"{published_at.date().isoformat()}-{stem}"


def _text(element: object) -> str:
    """`.text` of an ElementTree node, or "" — nodes are Optional and
    self-closing tags have text None."""
    value = getattr(element, "text", None)
    return value.strip() if isinstance(value, str) else ""


def _parse_timestamp(raw: str) -> datetime | None:
    """RFC 822 (RSS) or ISO 8601 (Atom), always returned tz-aware in UTC.

    A naive timestamp is treated as UTC rather than as local time: the
    worker runs in containers whose TZ we do not control, and guessing
    would silently shift every date by hours.
    """
    if not raw:
        return None
    for parse in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            parsed = parse(raw.replace("Z", "+00:00") if parse is datetime.fromisoformat else raw)
        except (TypeError, ValueError):
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def parse_feed(xml: str | bytes) -> list[FeedEntry]:
    """RSS 2.0, RSS 1.0/RDF and Atom into a single entry shape.

    Entries missing a title, a link or a publisher timestamp are dropped
    here — the card cannot render attribution without all three, and an
    invented date would be a lie about when something was published.
    """
    root = DefusedET.fromstring(xml)
    nodes = (
        root.findall(".//item")
        + root.findall(".//rss1:item", _NS)
        + root.findall(".//atom:entry", _NS)
    )

    entries: list[FeedEntry] = []
    for node in nodes:
        title = strip_html(_text(node.find("title")) or _text(node.find("atom:title", _NS)))

        link = _text(node.find("link"))
        if not link:
            # Atom puts the URL in an attribute, and may carry several
            # rel types; `alternate` (or a bare href) is the article.
            for candidate in node.findall("atom:link", _NS):
                if candidate.get("rel", "alternate") == "alternate":
                    link = (candidate.get("href") or "").strip()
                    break
        if not link:
            link = _text(node.find("guid"))

        published = _parse_timestamp(
            _text(node.find("pubDate"))
            or _text(node.find("dc:date", _NS))
            or _text(node.find("atom:published", _NS))
            or _text(node.find("atom:updated", _NS))
        )

        if not title or not link or published is None:
            continue

        summary = strip_html(
            _text(node.find("description"))
            or _text(node.find("atom:summary", _NS))
            or _text(node.find("rss1:description", _NS))
        )
        entries.append(
            FeedEntry(
                title=title,
                # Cards show two lines; storing a whole article body under
                # "summary" would also be republishing rather than linking.
                summary=summary[:400],
                url=link,
                published_at=published,
            )
        )
    return entries


async def fetch_feed(feed_url: str, *, client: httpx.AsyncClient | None = None) -> str:
    """Download a feed body, size-capped. Raises httpx errors upward — the
    caller records them as `fetch_failed` on the run row."""
    owned = client is None
    http = client or httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        response = await http.get(feed_url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        body = response.content[:MAX_FEED_BYTES]
        if len(response.content) > MAX_FEED_BYTES:
            log.warning("feed %s exceeded %d bytes; truncated", feed_url, MAX_FEED_BYTES)
        return body.decode(response.encoding or "utf-8", errors="replace")
    finally:
        if owned:
            await http.aclose()


async def ingest_source(
    session: AsyncSession,
    source: Source,
    *,
    client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
) -> IngestResult:
    """Read one source and record the attempt.

    Every path through this function writes an `content.ingest_runs` row,
    including the failures — a run that left no trace is indistinguishable
    from a worker that never fired (ADR-0012).
    """
    started = now or datetime.now(UTC)

    if not source.enabled:
        await _record_run(session, source.slug, started, IngestResult(OUTCOME_DISABLED))
        return IngestResult(OUTCOME_DISABLED)

    try:
        entries = parse_feed(await fetch_feed(source.feed_url, client=client))
    except Exception as exc:  # noqa: BLE001 — the outcome IS the handling
        log.warning("content ingest fetch failed for %s: %s", source.slug, exc)
        result = IngestResult(OUTCOME_FETCH_FAILED, error=f"{type(exc).__name__}: {exc}"[:500])
        await _record_run(session, source.slug, started, result)
        return result

    if not entries:
        result = IngestResult(OUTCOME_EMPTY)
        await _record_run(session, source.slug, started, result)
        return result

    written = duplicates = skipped = 0
    try:
        # Same story under two campaign URLs inside ONE feed would
        # otherwise pass the DB check twice before either was flushed.
        seen: set[str] = set()
        for entry in entries:
            canonical = normalise_url(entry.url)
            if not canonical.startswith(("http://", "https://")):
                skipped += 1
                continue
            if canonical in seen:
                duplicates += 1
                continue
            seen.add(canonical)

            existing = await session.scalar(
                select(ContentItem.id).where(ContentItem.canonical_url == canonical)
            )
            if existing is not None:
                duplicates += 1
                continue

            session.add(
                ContentItem(
                    kind=KIND_ARTICLE,
                    slug=slugify(entry.title, entry.published_at),
                    # Only the publisher's own language is real. The other
                    # locales stay ABSENT rather than being filled with the
                    # English string dressed up as a translation; the read
                    # path falls back to `en` and the card is honest.
                    title={"en": entry.title},
                    summary={"en": entry.summary},
                    source_id=source.id,
                    source_name=source.name,
                    source_url=source.homepage_url,
                    published_at=entry.published_at,
                    canonical_url=canonical,
                    verticals=list(source.verticals),
                    states=list(source.states),
                    # NOTE: moderation_status is deliberately NOT set.
                    # UGCMixin's `pending` default is the no-auto-publish
                    # guarantee, and naming it here would be the bug.
                )
            )
            written += 1
        await session.flush()
    except Exception as exc:  # noqa: BLE001
        log.warning("content ingest write failed for %s: %s", source.slug, exc)
        await session.rollback()
        result = IngestResult(
            OUTCOME_WRITE_FAILED, fetched=len(entries), error=f"{type(exc).__name__}: {exc}"[:500]
        )
        await _record_run(session, source.slug, started, result)
        return result

    result = IngestResult(
        OUTCOME_OK,
        fetched=len(entries),
        written=written,
        duplicates=duplicates,
        skipped=skipped,
    )
    await _record_run(session, source.slug, started, result)
    return result


async def _record_run(
    session: AsyncSession, source_slug: str, started: datetime, result: IngestResult
) -> None:
    session.add(
        IngestRun(
            source_slug=source_slug,
            started_at=started,
            finished_at=datetime.now(UTC),
            outcome=result.outcome,
            fetched=result.fetched,
            written=result.written,
            duplicates=result.duplicates,
            skipped=result.skipped,
            error=result.error,
        )
    )
    await session.flush()


async def ingest_all(
    session: AsyncSession, *, client: httpx.AsyncClient | None = None
) -> dict[str, IngestResult]:
    """Every enabled source, one at a time.

    Sequential on purpose: a handful of feeds is not worth the
    concurrency, and hitting several government portals at once from one
    IP is how a bot gets blocked.
    """
    sources = (await session.scalars(select(Source).where(Source.enabled.is_(True)))).all()
    return {source.slug: await ingest_source(session, source, client=client) for source in sources}
