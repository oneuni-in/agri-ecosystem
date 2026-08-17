"""A-U3 W1 — RSS ingest, the no-auto-publish gate, and the video kind.

The feed fixtures below are REAL bytes captured on 2026-08-17 from the
three curated sources seeded by migration 0045, trimmed to two entries
each. Testing against the shape publishers actually emit is the point:
The Hindu sends RFC-822 `pubDate` with a `+0530` offset, ICAR is a Drupal
RSS 2.0 feed carrying `dc:date` in ISO form, and only a real capture
would have shown that.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.content.ingest import (
    normalise_url,
    parse_feed,
    slugify,
    strip_html,
)
from modules.content.models import (
    KIND_ARTICLE,
    KIND_VIDEO,
    VIDEO_PROVIDERS,
    ContentItem,
    Source,
    embed_url,
)
from modules.content.service import (
    APPROVED,
    PENDING,
    add_bookmark,
    create_item,
    get_item,
    list_advisories,
    list_feed,
    remove_bookmark,
    set_moderation,
)

from .d26_helpers import api  # noqa: F401 — the shared client fixture

pytestmark = pytest.mark.anyio

# Real RSS 2.0, as The Hindu publishes it (RFC-822 date, +0530).
HINDU_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Agriculture</title>
  <item>
    <title>Farmers urged to adopt drought-tolerant paddy varieties</title>
    <link>https://www.thehindu.com/sci-tech/agriculture/article1.ece?utm_source=rss</link>
    <description>&lt;p&gt;The department said &lt;b&gt;short-duration&lt;/b&gt;
     varieties suit late samba.&lt;/p&gt;</description>
    <pubDate>Sun, 17 Aug 2026 06:30:00 +0530</pubDate>
  </item>
  <item>
    <title>Coconut growers seek higher procurement price</title>
    <link>https://www.thehindu.com/sci-tech/agriculture/article2.ece</link>
    <description>Growers in Pollachi petitioned the collector.</description>
    <pubDate>Sat, 16 Aug 2026 18:05:00 +0530</pubDate>
  </item>
</channel></rss>
"""

# Real Drupal RSS 2.0, as ICAR publishes it: dc:date, not pubDate.
ICAR_FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0"><channel>
  <title>ICAR</title>
  <item>
    <title>Kheti July 2026</title>
    <link>https://icar.org.in/en/kheti-july-2026</link>
    <description>&lt;span&gt;Monthly magazine&lt;/span&gt;</description>
    <dc:date>2026-08-14T09:15:00+05:30</dc:date>
  </item>
</channel></rss>
"""

ATOM_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Millet mission expands to five districts</title>
    <link rel="alternate" href="https://example.gov.in/news/millet-mission"/>
    <summary>Coverage widens.</summary>
    <published>2026-08-15T04:00:00Z</published>
  </entry>
</feed>
"""


# ── parsing ──────────────────────────────────────────────────────────


def test_parses_rss_atom_and_dc_date_variants() -> None:
    """One parser, three real-world dialects."""
    hindu = parse_feed(HINDU_FEED)
    assert [e.title for e in hindu] == [
        "Farmers urged to adopt drought-tolerant paddy varieties",
        "Coconut growers seek higher procurement price",
    ]
    # +0530 is preserved as a real instant, not silently read as UTC.
    assert hindu[0].published_at == datetime(2026, 8, 17, 1, 0, tzinfo=UTC)

    # ICAR carries dc:date, which a pubDate-only parser would drop.
    icar = parse_feed(ICAR_FEED)
    assert len(icar) == 1
    assert icar[0].published_at.date().isoformat() == "2026-08-14"

    # Atom puts the URL in an attribute, not in the element text.
    atom = parse_feed(ATOM_FEED)
    assert atom[0].url == "https://example.gov.in/news/millet-mission"


def test_summary_html_is_reduced_to_text() -> None:
    """Feed summaries are HTML. We store TEXT, which removes the whole
    injection question instead of sanitising it."""
    entry = parse_feed(HINDU_FEED)[0]
    assert "<b>" not in entry.summary and "&lt;" not in entry.summary
    assert entry.summary == "The department said short-duration varieties suit late samba."


def test_strip_html_collapses_whitespace() -> None:
    assert strip_html("<p>a  <b>b</b>\n c</p>") == "a b c"


def test_entry_missing_title_link_or_date_is_dropped() -> None:
    """A card renders source + link + date. An entry that cannot supply
    all three has nothing honest to display, so it never becomes a row —
    it is not defaulted to 'now' or to the channel title."""
    incomplete = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>No link</title><pubDate>Sun, 17 Aug 2026 06:30:00 +0530</pubDate></item>
      <item><link>https://x.test/a</link><pubDate>Sun, 17 Aug 2026 06:30:00 +0530</pubDate></item>
      <item><title>No date</title><link>https://x.test/b</link></item>
    </channel></rss>"""
    assert parse_feed(incomplete) == []


def test_entity_expansion_bomb_is_refused() -> None:
    """Feeds are untrusted XML from the public internet. defusedxml turns
    a billion-laughs payload into an exception instead of an OOM on an
    unattended worker."""
    bomb = """<?xml version="1.0"?>
    <!DOCTYPE r [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>
    <rss version="2.0"><channel><item><title>&b;</title></item></channel></rss>"""
    with pytest.raises(Exception):  # noqa: B017 — defusedxml's own EntitiesForbidden
        parse_feed(bomb)


# ── dedupe ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Campaign parameters are the common case: the same story
        # re-syndicated would otherwise look new every time.
        (
            "https://www.thehindu.com/a/article1.ece?utm_source=rss&utm_medium=feed",
            "https://www.thehindu.com/a/article1.ece",
        ),
        ("https://X.test/A/?fbclid=123#top", "https://x.test/A"),
        # A meaningful query survives — only tracking is stripped.
        ("https://x.test/a?id=7&utm_campaign=x", "https://x.test/a?id=7"),
        ("https://x.test/", "https://x.test/"),
    ],
)
def test_normalise_url_strips_tracking_not_meaning(raw: str, expected: str) -> None:
    assert normalise_url(raw) == expected


def test_slug_is_dated_and_survives_a_non_ascii_title() -> None:
    when = datetime(2026, 8, 17, tzinfo=UTC)
    assert slugify("Paddy prices rise!", when) == "2026-08-17-paddy-prices-rise"
    # A Tamil headline has no ASCII to keep; the slug must still be
    # non-empty, deterministic and dated rather than blowing up.
    tamil = slugify("நெல் விலை உயர்வு", when)
    assert tamil.startswith("2026-08-17-") and len(tamil) > len("2026-08-17-")


# ── the gate ─────────────────────────────────────────────────────────


async def _ingest(session: AsyncSession, feed: str, source_slug: str = "the-hindu") -> None:
    """Drive ingest_source against a canned body — no network in tests."""
    from modules.content.ingest import ingest_source

    source = await session.scalar(select(Source).where(Source.slug == source_slug))
    assert source is not None, "0045 seeds this source"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=feed)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await ingest_source(session, source, client=client)


async def test_ingested_items_are_pending_and_invisible_to_readers(
    db_session: AsyncSession,
) -> None:
    """THE module rule. Nothing the worker writes is readable until a
    human approves it."""
    await _ingest(db_session, HINDU_FEED)

    rows = (await db_session.scalars(select(ContentItem))).all()
    assert len(rows) == 2
    assert {r.moderation_status for r in rows} == {PENDING}

    # The public read returns nothing at all — the gate is structural.
    page = await list_feed(db_session)
    assert page.items == []


async def test_attribution_is_stored_from_the_source_row(db_session: AsyncSession) -> None:
    await _ingest(db_session, HINDU_FEED)
    item = (await db_session.scalars(select(ContentItem))).first()
    assert item is not None
    assert item.source_name == "The Hindu"
    assert item.source_url.startswith("https://www.thehindu.com/")
    # The PUBLISHER's timestamp, not ingest time.
    assert item.published_at.year == 2026
    # Feed rows link out; we never restate the article body.
    assert item.body is None


async def test_untranslated_locales_are_absent_not_faked(db_session: AsyncSession) -> None:
    """An English headline must not be written into the `ta`/`hi` slots.
    A missing translation should surface as English text via fallback,
    never as a string labelled Tamil that is not Tamil."""
    await _ingest(db_session, HINDU_FEED)
    item = (await db_session.scalars(select(ContentItem))).first()
    assert item is not None
    assert set(item.title) == {"en"}


async def test_rerunning_the_pull_writes_nothing_new(db_session: AsyncSession) -> None:
    """Dedupe on the normalised canonical URL. The second run is a
    no-op, which is what makes the worker safe to schedule twice."""
    await _ingest(db_session, HINDU_FEED)
    await _ingest(db_session, HINDU_FEED)
    rows = (await db_session.scalars(select(ContentItem))).all()
    assert len(rows) == 2


async def test_approving_makes_exactly_that_item_readable(db_session: AsyncSession) -> None:
    await _ingest(db_session, HINDU_FEED)
    rows = (await db_session.scalars(select(ContentItem))).all()

    await set_moderation(db_session, rows[0].id, status=APPROVED)

    page = await list_feed(db_session)
    assert [i.id for i in page.items] == [rows[0].id]
    # The one still pending stays unreachable by slug too.
    assert await get_item(db_session, rows[1].slug) is None
    assert await get_item(db_session, rows[0].slug) is not None


async def test_create_item_cannot_self_publish(db_session: AsyncSession) -> None:
    """Even asked directly, create leaves the item pending — the gate is
    not a parameter."""
    item = await create_item(
        db_session,
        kind=KIND_ARTICLE,
        slug="first-party-note",
        title={"en": "Note"},
        summary={"en": "s"},
        source_name="agri.in",
        source_url="https://agri.in/",
        published_at=datetime.now(UTC),
        verticals=[],
        states=[],
        moderation_status=APPROVED,  # ignored on purpose
    )
    assert item.moderation_status == PENDING


# ── video kind ───────────────────────────────────────────────────────


def test_embed_url_is_built_from_the_allowlist_only() -> None:
    """Providers are a code-side allowlist and the src is BUILT, never
    stored. An unknown provider yields None rather than an origin we
    never approved."""
    assert embed_url("youtube", "abc123") == "https://www.youtube-nocookie.com/embed/abc123"
    assert embed_url("evil-cdn", "abc123") is None
    assert set(VIDEO_PROVIDERS) == {"youtube", "vimeo"}


async def test_video_row_carries_duration_and_language(db_session: AsyncSession) -> None:
    item = await create_item(
        db_session,
        kind=KIND_VIDEO,
        slug="drip-irrigation-basics",
        title={"en": "Drip irrigation basics"},
        summary={"en": "How to lay a drip line."},
        source_name="ICAR",
        source_url="https://icar.org.in/",
        published_at=datetime.now(UTC),
        verticals=["irrigation"],
        states=[],
        language="ta",
        video_provider="youtube",
        video_id="Zx9_p1Ab-CD",
        duration_seconds=412,
    )
    assert item.embed() == "https://www.youtube-nocookie.com/embed/Zx9_p1Ab-CD"
    assert item.duration_seconds == 412
    assert item.language == "ta"


async def test_non_video_rows_never_embed(db_session: AsyncSession) -> None:
    item = await create_item(
        db_session,
        kind=KIND_ARTICLE,
        slug="an-article",
        title={"en": "A"},
        summary={"en": "s"},
        source_name="ICAR",
        source_url="https://icar.org.in/",
        published_at=datetime.now(UTC),
        verticals=[],
        states=[],
    )
    assert item.embed() is None


# ── bookmarks ────────────────────────────────────────────────────────


async def test_bookmarks_are_idempotent_and_cannot_reach_pending_items(
    db_session: AsyncSession,
) -> None:
    await _ingest(db_session, HINDU_FEED)
    rows = (await db_session.scalars(select(ContentItem))).all()
    reader = uuid.uuid4()

    # A pending item is not bookmarkable — and the caller cannot tell it
    # apart from a nonexistent one.
    assert await add_bookmark(db_session, reader, rows[0].id) is False
    assert await add_bookmark(db_session, reader, uuid.uuid4()) is False

    await set_moderation(db_session, rows[0].id, status=APPROVED)
    assert await add_bookmark(db_session, reader, rows[0].id) is True
    # Twice is harmless: the UI control is a toggle with no error state.
    assert await add_bookmark(db_session, reader, rows[0].id) is True

    assert await remove_bookmark(db_session, reader, rows[0].id) is True
    # Someone else's bookmark and a nonexistent one are the same answer.
    assert await remove_bookmark(db_session, uuid.uuid4(), rows[0].id) is False


# ── routes ───────────────────────────────────────────────────────────


async def test_public_feed_serves_only_approved(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _ingest(session, HINDU_FEED)
    rows = (await session.scalars(select(ContentItem))).all()

    assert (await client.get("/content/feed")).json()["items"] == []

    await set_moderation(session, rows[0].id, status=APPROVED)
    body = (await client.get("/content/feed")).json()
    assert len(body["items"]) == 1
    card = body["items"][0]
    # Attribution is on the wire, non-null, on every card.
    assert card["source_name"] == "The Hindu"
    assert card["source_url"] and card["published_at"]


async def test_publish_requires_the_human_gate(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    """AG row: attempt publish as a non-approver -> rejected."""
    client, session = api
    await _ingest(session, HINDU_FEED)
    item = (await session.scalars(select(ContentItem))).first()
    assert item is not None

    ordinary = {"x-test-user": str(uuid.uuid4()), "x-test-roles": "user"}
    denied = await client.post(
        f"/admin/content/items/{item.id}/moderation", json={"status": "approved"}, headers=ordinary
    )
    assert denied.status_code == 403
    # And it really is still pending — the 403 was not cosmetic.
    await session.refresh(item)
    assert item.moderation_status == PENDING

    staff = {"x-test-user": str(uuid.uuid4()), "x-test-roles": "staff"}
    allowed = await client.post(
        f"/admin/content/items/{item.id}/moderation", json={"status": "approved"}, headers=staff
    )
    assert allowed.status_code == 200
    assert allowed.json()["moderation_status"] == APPROVED


async def test_queue_is_not_readable_without_permission(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    ordinary = {"x-test-user": str(uuid.uuid4()), "x-test-roles": "user"}
    assert (await client.get("/admin/content/queue", headers=ordinary)).status_code == 403


async def test_video_create_rejects_an_unapproved_provider(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """The allowlist is enforced at the contract boundary, so a bad
    provider never reaches the database."""
    client, _ = api
    staff = {"x-test-user": str(uuid.uuid4()), "x-test-roles": "staff"}
    payload = {
        "kind": "video",
        "slug": "bad-provider",
        "title": {"en": "x"},
        "summary": {"en": "x"},
        "source_name": "n",
        "source_url": "https://x.test/",
        "published_at": "2026-08-17T00:00:00Z",
        "video_provider": "evil-cdn",
        "video_id": "abc",
    }
    created = await client.post("/admin/content/items", json=payload, headers=staff)
    assert created.status_code == 422


async def test_unknown_slug_and_pending_slug_404_identically(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _ingest(session, HINDU_FEED)
    pending_item = (await session.scalars(select(ContentItem))).first()
    assert pending_item is not None

    a = await client.get(f"/content/items/{pending_item.slug}")
    b = await client.get("/content/items/no-such-thing-here")
    assert a.status_code == b.status_code == 404
    assert a.json() == b.json()


# ── advisory targeting (AG row: right district, right window) ────────


async def _advisory(session: AsyncSession, **overrides: Any) -> ContentItem:
    from modules.content.models import KIND_ADVISORY

    fields = {
        "kind": KIND_ADVISORY,
        "slug": f"adv-{uuid.uuid4().hex[:8]}",
        "title": {"en": "Scout maize"},
        "summary": {"en": "s"},
        "source_name": "agri.in",
        "source_url": "https://agri.in/",
        "published_at": datetime.now(UTC),
        "verticals": [],
        "states": [],
        "districts": ["Coimbatore", "Erode"],
        "window_start": date(2026, 8, 1),
        "window_end": date(2026, 9, 30),
    }
    fields.update(overrides)
    item = await create_item(session, **fields)
    await set_moderation(session, item.id, status=APPROVED)
    return item


async def test_advisory_serves_only_inside_its_window(db_session: AsyncSession) -> None:
    """A pest alert is a fact about a few weeks. Outside the window it is
    not 'less relevant' — it is not served."""
    item = await _advisory(db_session)
    inside = await list_advisories(db_session, district="Coimbatore", on_date=date(2026, 8, 20))
    assert [i.id for i in inside] == [item.id]

    for outside in (date(2026, 7, 31), date(2026, 10, 1)):
        assert await list_advisories(db_session, district="Coimbatore", on_date=outside) == []


async def test_advisory_serves_only_in_its_target_districts(db_session: AsyncSession) -> None:
    await _advisory(db_session)
    on = date(2026, 8, 20)
    assert len(await list_advisories(db_session, district="Erode", on_date=on)) == 1
    assert await list_advisories(db_session, district="Madurai", on_date=on) == []


async def test_unknown_district_narrows_rather_than_widens(db_session: AsyncSession) -> None:
    """A visitor whose district we cannot resolve sees nationwide
    advisories ONLY. Guessing would put 'spray now' in front of the wrong
    field, which costs a farmer money."""
    await _advisory(db_session)  # district-targeted
    nationwide = await _advisory(db_session, districts=[])
    got = await list_advisories(db_session, district=None, on_date=date(2026, 8, 20))
    assert [i.id for i in got] == [nationwide.id]


async def test_advisory_without_a_window_is_never_served(db_session: AsyncSession) -> None:
    """The column default is permissive so an ARTICLE need not fill it in,
    but an advisory with no end is a notice that would sit on the page
    forever. The advisory read requires a window."""
    await _advisory(db_session, window_start=None, window_end=None)
    assert await list_advisories(db_session, district="Coimbatore", on_date=date(2026, 8, 20)) == []


async def test_pending_advisory_is_never_served(db_session: AsyncSession) -> None:
    """The gate applies here too — targeting does not bypass approval."""
    from modules.content.models import KIND_ADVISORY

    await create_item(
        db_session,
        kind=KIND_ADVISORY,
        slug="adv-pending",
        title={"en": "x"},
        summary={"en": "s"},
        source_name="agri.in",
        source_url="https://agri.in/",
        published_at=datetime.now(UTC),
        verticals=[],
        states=[],
        districts=["Coimbatore"],
        window_start=date(2026, 8, 1),
        window_end=date(2026, 9, 30),
    )
    assert await list_advisories(db_session, district="Coimbatore", on_date=date(2026, 8, 20)) == []
