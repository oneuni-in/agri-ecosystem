/**
 * A-U3 W1 — the knowledge/news surfaces' data layer.
 *
 * Same contract as `lib/home.ts` and `lib/mandi.ts`: every fetch is
 * server-side, public-read, and swallows failure into `null`/`[]`. A dead
 * content engine costs the section, never the page (F1 rule).
 *
 * The honesty rule has a concrete shape here. The backend serves APPROVED
 * items only, so an empty array means one of two things — the module is
 * empty, or nothing has been approved yet — and both render identically:
 * the section is ABSENT. There is no empty-state card for knowledge,
 * because "we have no articles" is not something a reader needs told.
 */
// Pure formatters live in @agri/ui (tested there — web-agri has no
// runner). Re-exported so call sites keep one import for the module.
export { extractFaq, formatDuration } from "@agri/ui";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * Editorial content changes when a human approves something, which is
 * rare and never urgent. Five minutes matches the home's other reads.
 */
const REVALIDATE_SECONDS = 300;

export type ContentKind = "article" | "video" | "guide" | "advisory";

export interface ContentCard {
  id: string;
  kind: ContentKind;
  slug: string;
  title: Record<string, string>;
  summary: Record<string, string>;
  /** Attribution — all three always present, all three rendered. */
  source_name: string;
  source_url: string;
  published_at: string;
  /** The publisher's own URL. Null for first-party items. */
  canonical_url: string | null;
  verticals: string[];
  states: string[];
  /** Language of the linked material, not of the card's title. */
  language: string;
  /** Video only. Null everywhere else — never render a duration pill. */
  duration_seconds: number | null;
  video_provider: string | null;
  /** Built server-side from the provider allowlist; never client-supplied. */
  embed_url: string | null;
  bookmarked: boolean;
}

export interface ContentDetail extends ContentCard {
  body: Record<string, string> | null;
}

export interface ContentPage {
  items: ContentCard[];
  next_cursor: string | null;
}

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, {
      next: { revalidate: REVALIDATE_SECONDS },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export interface FeedQuery {
  kind?: ContentKind;
  vertical?: string;
  cursor?: string;
  limit?: number;
}

/** Approved items, newest first. `[]` on any failure — the caller's
 * section then renders absent rather than broken. */
export async function fetchFeed(query: FeedQuery = {}): Promise<ContentPage> {
  const params = new URLSearchParams();
  if (query.kind) params.set("kind", query.kind);
  if (query.vertical) params.set("vertical", query.vertical);
  if (query.cursor) params.set("cursor", query.cursor);
  params.set("limit", String(query.limit ?? 20));
  return (
    (await getJson<ContentPage>(`/content/feed?${params}`)) ?? {
      items: [],
      next_cursor: null,
    }
  );
}

/** One approved item. `null` for pending, rejected or unknown alike — the
 * page 404s on all three, so a slug guess reveals nothing. */
export async function fetchContentItem(
  slug: string,
): Promise<ContentDetail | null> {
  return getJson<ContentDetail>(`/content/items/${encodeURIComponent(slug)}`);
}

/**
 * The home's §11 block: curated cards on the left, a news rail on the right.
 *
 * Returned together, and deduped against each other, because they are one
 * section: the A1 reference shows guides/advisories/video as cards and
 * NEWS as the rail, and the two must never show the same story twice.
 * Building them from separate calls at the call site is exactly how that
 * duplication happens.
 *
 * Cards are ordered by `published_at` alone — recency wins, kind never
 * outranks it (AG-A65). The old rule concatenated video → guide →
 * advisory → article, which meant three curated items of any age locked
 * the newest article out of the cards forever. The card treatment keeps
 * its video play tile; videos just compete on date like everything else.
 */
export async function fetchKnowledgeSection(
  cardLimit = 3,
  newsLimit = 6,
): Promise<{ cards: ContentCard[]; news: ContentCard[] }> {
  const [videos, guides, advisories, articles] = await Promise.all([
    fetchFeed({ kind: "video", limit: cardLimit }),
    fetchFeed({ kind: "guide", limit: cardLimit }),
    fetchFeed({ kind: "advisory", limit: cardLimit }),
    fetchFeed({ kind: "article", limit: newsLimit + cardLimit }),
  ]);

  const cards = [
    ...videos.items,
    ...guides.items,
    ...advisories.items,
    ...articles.items,
  ]
    .sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at))
    .slice(0, cardLimit);

  // The rail shows news the cards did not already take. It never pads
  // itself back to newsLimit with something already on screen.
  const shown = new Set(cards.map((item) => item.id));
  const news = articles.items
    .filter((item) => !shown.has(item.id))
    .slice(0, newsLimit);
  return { cards, news };
}

/** Locale pick with an English fallback — the same rule every other
 * TranslatedText surface uses. A missing Tamil title shows the English
 * one, which is honest; an empty card would not be. */
export function pick(
  locale: string,
  text: Record<string, string> | null | undefined,
): string {
  if (!text) return "";
  return text[locale] ?? text["en"] ?? "";
}
