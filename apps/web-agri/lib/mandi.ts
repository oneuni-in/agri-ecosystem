/**
 * A-U2 W3 — the mandi commodity pages' data layer.
 *
 * Same contract as `lib/home.ts`: every fetch is server-side, public-read,
 * and swallows failure into `null`/`[]`. A dead engine degrades a page to
 * its empty state or a 404; it never 500s (F1 rule).
 *
 * These pages are NOT behind `agri_today`. That flag is the home Today
 * strip's kill switch; pulling indexed pages out from under Google is a
 * different decision, so the backend serves these routes ungated.
 */
const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** Prices move once a day, so an hour of staleness costs nothing and
 * spares the API a read per visitor. The as-of stamp travels IN the
 * payload, so a cached page still tells the truth about its own age. */
const REVALIDATE_SECONDS = 3600;

export interface CommodityListItem {
  slug: string;
  name: Record<string, string>;
  emoji: string;
  unit: string;
  market_count: number;
  /** ISO date of the newest ingested day; "" when nothing is ingested. */
  as_of: string;
}

export interface MarketPrice {
  market_slug: string;
  market: string;
  district: string;
  price: number;
  /** Signed day-over-day delta; 0 renders flat. */
  change: number;
  /** Oldest first — the sparkline input. One point means no line yet. */
  series_30d: number[];
  range_low: number;
  range_high: number;
  modal: number | null;
  as_of: string;
}

export interface CommodityDetail {
  slug: string;
  name: Record<string, string>;
  emoji: string;
  unit: string;
  source: string;
  as_of: string;
  /** MSP overlay — present only where a verified row exists. */
  note: Record<string, string> | null;
  markets: MarketPrice[];
}

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, { next: { revalidate: REVALIDATE_SECONDS } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/** Commodities that actually have servable prices. The backend omits the
 * empty ones, so this doubles as the sitemap's source: a page with no
 * data is never advertised. */
export async function fetchCommodities(): Promise<CommodityListItem[]> {
  return (await getJson<CommodityListItem[]>("/market/commodities")) ?? [];
}

/** One commodity across every market that reported it. `null` for an
 * uncurated slug OR one with no rows — the page 404s on both. */
export async function fetchCommodity(slug: string): Promise<CommodityDetail | null> {
  return getJson<CommodityDetail>(`/market/commodities/${encodeURIComponent(slug)}`);
}

/** Locale pick with an English fallback — the same rule the home uses for
 * every TranslatedText. */
export function pick(locale: string, text: Record<string, string> | null | undefined): string {
  if (!text) return "";
  return text[locale] ?? text["en"] ?? "";
}
