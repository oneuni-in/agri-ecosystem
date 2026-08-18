"""A-U4 W1 — rebuild the assistant's retrieval corpus.

    python scripts/ai_ingest.py

Reads content's PUBLIC feed, chunks each item, embeds the chunks locally and
replaces `ai.chunks` wholesale.

WHY THE PUBLIC FEED AND NOT THE TABLE. `modules.ai` may not import
`modules.content` (import-linter independence) and may not read another
module's tables. Going through `GET /content/feed` is the way that constraint
is satisfied — and it turns into the safety property that matters most here:
the feed serves APPROVED items only, so the corpus inherits A-U3's human
curation gate BY CONSTRUCTION. There is no query in this file that could
retrieve a pending article, because the ingest is never shown one.

WHY REPLACE RATHER THAN UPSERT. The corpus is derived and small. A full
rebuild means an item that was un-approved, edited or deleted upstream simply
stops existing here on the next run — no tombstones, no drift between what
/knowledge shows and what the assistant can cite. Incremental sync would buy
speed we do not need and cost a class of staleness bug we would rather not
own.

The rebuild happens in ONE transaction: the old corpus is only deleted if the
new one embedded successfully, so a failed run leaves the previous corpus
serving rather than emptying it.
"""

from __future__ import annotations

import asyncio
import re
import sys
from typing import Any

import httpx
import uuid6
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(__file__).rsplit("scripts", 1)[0])

from modules.ai.embedding import embed_passages, embedding_available  # noqa: E402
from modules.ai.models import Chunk  # noqa: E402
from settings import get_settings  # noqa: E402

#: Characters per chunk. Small enough that a citation points at something a
#: reader can find on the page, large enough to keep a paragraph's meaning
#: intact. Guides are the long documents here; news items usually fit whole.
CHUNK_CHARS = 900
CHUNK_OVERLAP = 150


def _clean(text: str) -> str:
    """Strip markup and collapse whitespace. Feed bodies arrive as HTML from
    the public internet and we embed prose, not tags."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _chunk(text: str) -> list[str]:
    text = _clean(text)
    if len(text) <= CHUNK_CHARS:
        return [text] if text else []
    out: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_CHARS
        # Prefer a sentence boundary so a chunk does not start mid-clause.
        if end < len(text):
            dot = text.rfind(". ", start + CHUNK_CHARS // 2, end)
            if dot != -1:
                end = dot + 1
        out.append(text[start:end].strip())
        start = max(end - CHUNK_OVERLAP, end)
    return [c for c in out if c]


def _pick(value: Any) -> str:
    """TranslatedText -> a string to embed. English is the embedding model's
    language; the vernacular titles still render on the citation from the
    content row, so nothing is lost to the reader."""
    if isinstance(value, dict):
        return str(value.get("en") or next(iter(value.values()), ""))
    return str(value or "")


async def _fetch_all() -> list[dict[str, Any]]:
    """Walk the cursor-paginated public feed. Bounded: a runaway upstream
    must not spin here forever."""
    settings = get_settings()
    base = settings.internal_api_base_url.rstrip("/")
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for _ in range(50):
            qs = f"?limit=50&cursor={cursor}" if cursor else "?limit=50"
            res = await client.get(f"{base}/content/feed{qs}")
            res.raise_for_status()
            body = res.json()
            items.extend(body.get("items") or [])
            cursor = body.get("next_cursor")
            if not cursor:
                break
    return items


async def main() -> int:
    if not embedding_available():
        print("fastembed unavailable — install it or bake the model into the image")  # noqa: T201
        return 2

    items = await _fetch_all()
    print(f"feed returned {len(items)} approved items")  # noqa: T201

    rows: list[Chunk] = []
    passages: list[str] = []
    for item in items:
        title = _pick(item.get("title"))
        body = _pick(item.get("body")) or _pick(item.get("summary"))
        if not body:
            # A video row has no prose to retrieve. Skipping it is honest:
            # an entry embedded from its title alone would match queries it
            # cannot actually answer.
            continue
        for ordinal, passage in enumerate(_chunk(f"{title}. {body}")):
            rows.append(
                Chunk(
                    id=uuid6.uuid7(),
                    source_id=item["id"],
                    source_slug=item.get("slug", ""),
                    source_name=item.get("source_name", "agri.in"),
                    title=title,
                    kind=item.get("kind", "article"),
                    ordinal=ordinal,
                    body=passage,
                )
            )
            passages.append(passage)

    if not rows:
        print("nothing to embed — corpus left unchanged")  # noqa: T201
        return 1

    vectors = embed_passages(passages)
    for row, vector in zip(rows, vectors, strict=True):
        row.embedding = vector

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        # Delete + insert in ONE transaction: a failed embed above never
        # reaches here, so the previous corpus keeps serving.
        await session.execute(delete(Chunk))
        session.add_all(rows)
        await session.commit()
    await engine.dispose()

    print(f"embedded {len(rows)} chunks from {len(items)} items")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
