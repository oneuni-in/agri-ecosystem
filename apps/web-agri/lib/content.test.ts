import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchKnowledgeSection } from "./content";
import type { ContentCard, ContentKind } from "./content";

afterEach(() => vi.unstubAllGlobals());

function card(kind: ContentKind, slug: string, publishedAt: string): ContentCard {
  return {
    id: slug,
    kind,
    slug,
    title: { en: slug },
    summary: { en: slug },
    source_name: "src",
    source_url: "https://example.org",
    published_at: publishedAt,
    canonical_url: null,
    verticals: [],
    states: [],
    language: "en",
    duration_seconds: null,
    video_provider: null,
    embed_url: null,
    bookmarked: false,
  };
}

/** Serves /content/feed by its `kind` query param, newest-first per kind —
 * exactly what the backend contract guarantees (service.py orders
 * published_at DESC). */
function stubFeeds(byKind: Partial<Record<ContentKind, ContentCard[]>>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input));
      const kind = url.searchParams.get("kind") as ContentKind;
      return Promise.resolve({
        ok: true,
        json: async () => ({ items: byKind[kind] ?? [], next_cursor: null }),
      });
    }),
  );
}

describe("AG-A65: knowledge cards order by published_at, kind never outranks recency", () => {
  it("a newer article outranks an older guide in the cards", async () => {
    stubFeeds({
      guide: [card("guide", "old-guide", "2026-08-01T00:00:00Z")],
      article: [
        card("article", "fresh-article", "2026-08-19T00:00:00Z"),
        card("article", "stale-article", "2026-07-01T00:00:00Z"),
      ],
    });
    const { cards } = await fetchKnowledgeSection(2, 6);
    expect(cards.map((c) => c.slug)).toEqual(["fresh-article", "old-guide"]);
  });

  it("three curated items can no longer lock the newest article out", async () => {
    stubFeeds({
      video: [card("video", "v", "2026-06-01T00:00:00Z")],
      guide: [card("guide", "g", "2026-06-02T00:00:00Z")],
      advisory: [card("advisory", "a", "2026-06-03T00:00:00Z")],
      article: [card("article", "news", "2026-08-19T00:00:00Z")],
    });
    const { cards } = await fetchKnowledgeSection(3, 6);
    expect(cards[0]?.slug).toBe("news");
  });

  it("the rail still skips whatever the cards took, in feed order", async () => {
    stubFeeds({
      article: [
        card("article", "n1", "2026-08-19T00:00:00Z"),
        card("article", "n2", "2026-08-18T00:00:00Z"),
        card("article", "n3", "2026-08-17T00:00:00Z"),
      ],
    });
    const { cards, news } = await fetchKnowledgeSection(1, 6);
    expect(cards.map((c) => c.slug)).toEqual(["n1"]);
    expect(news.map((c) => c.slug)).toEqual(["n2", "n3"]);
  });

  it("a dead engine still costs the section, never the page (F1)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("ECONNREFUSED"))),
    );
    expect(await fetchKnowledgeSection()).toEqual({ cards: [], news: [] });
  });
});
