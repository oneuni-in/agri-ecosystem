import { parseLocCookie } from "@agri/ui";

import { DEFAULT_LOCATION } from "./default-location";
import { fetchMilkHome, type MilkCard, type MilkHome } from "./milk";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * The visitor's pincode for this render: their `agri_loc` cookie (D19 — set
 * by the header pill, the §4 pincode box, or GPS) falling back to
 * `DEFAULT_LOCATION`.
 *
 * Reading the cookie is what makes the home render "based on the header
 * pincode". It also makes the route dynamic, which is why the location-bound
 * sections stream behind a Suspense boundary in `page.tsx` — the shell, hero
 * and search band do not wait on this.
 */
export function resolveHomePincode(cookieValue: string | undefined): string {
  return parseLocCookie(cookieValue)?.pincode ?? DEFAULT_LOCATION.pincode;
}

/** §16: "if a stat is embarrassing pre-launch, hide that cell via config,
 * don't fake it." Comma-separated stat keys to hide. */
const HIDDEN_STATS = new Set(
  (process.env.HOME_HIDDEN_STATS ?? "").split(",").map((s) => s.trim()).filter(Boolean),
);
export function statVisible(key: string): boolean {
  return !HIDDEN_STATS.has(key);
}

export interface ReviewItem {
  id: string;
  rating: number;
  body: Record<string, string>;
  business: { name: string; slug: string };
}

export interface RatingSummary {
  rating_avg: string | null;
  rating_count: number;
}

export interface HomeData {
  home: MilkHome | null;
  /** business id → live D18 aggregate (rating + count) for the vendor cards. */
  ratings: Record<string, RatingSummary>;
  /** §8d — approved reviews only, composed across the businesses on this page. */
  reviews: ReviewItem[];
  /** §8e / §8b — real covered-pincode feed (D28 sitemap source). */
  coveredPincodes: { pincode: string; district: string }[];
}

async function getJson<T>(path: string, revalidate = 300): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, { next: { revalidate } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/** Walks the cursor-paginated coverage feed. Bounded: the sitemap feed caps a
 * page at 100, and 5 pages is far more coverage than the stat needs — a
 * runaway walk on a growing table is not worth a stat. */
async function fetchCoveredPincodes(): Promise<{ pincode: string; district: string }[]> {
  const out: { pincode: string; district: string }[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < 5; page++) {
    const qs: string = cursor ? `?cursor=${encodeURIComponent(cursor)}&limit=100` : "?limit=100";
    const body = await getJson<{
      items: { pincode: string; district: string }[];
      next_cursor: string | null;
    }>(`/catalog/milk/coverage/pincodes${qs}`, 3600);
    if (!body) break;
    out.push(...body.items);
    if (!body.next_cursor) break;
    cursor = body.next_cursor;
  }
  return out;
}

/**
 * ONE server-side aggregate for the whole home page (§16's "one cached
 * aggregate endpoint or server-side props; never client-computed from full
 * lists"). Every section below the hero renders from this — there is no
 * client fetch and no mock data anywhere on the page.
 *
 * Reviews: D18 exposes reviews per target, not as a global feed, and U1
 * forbids new API surface. So the strip is COMPOSED from the businesses
 * already on this page — approved-only comes from the engine itself, which
 * only ever returns approved rows to a public caller.
 */
export async function fetchHomeData(pincode: string): Promise<HomeData> {
  const [home, coveredPincodes] = await Promise.all([
    fetchMilkHome(pincode),
    fetchCoveredPincodes(),
  ]);

  const cards: MilkCard[] = [...(home?.vendors ?? []), ...(home?.brands ?? [])];
  const ratings: Record<string, RatingSummary> = {};
  const reviews: ReviewItem[] = [];

  const perCard = await Promise.all(
    cards.map(async (card) => {
      const query = `target_type=business&target_id=${encodeURIComponent(card.id)}`;
      const [summary, list] = await Promise.all([
        getJson<RatingSummary>(`/reviews/summary?${query}`),
        getJson<{ items: { id: string; rating: number; body: Record<string, string> }[] }>(
          `/reviews?${query}&limit=2`,
        ),
      ]);
      return { card, summary, list };
    }),
  );

  for (const { card, summary, list } of perCard) {
    if (summary) ratings[card.id] = summary;
    for (const item of list?.items ?? []) {
      reviews.push({
        id: item.id,
        rating: item.rating,
        body: item.body,
        business: { name: card.name, slug: card.slug },
      });
    }
  }

  // Highest-rated first so the strip leads with the strongest social proof,
  // then a stable id tiebreak so ISR revalidations don't reshuffle the page.
  reviews.sort((a, b) => b.rating - a.rating || a.id.localeCompare(b.id));

  return { home, ratings, reviews, coveredPincodes };
}

/** §8b stats — every number traced to a real source, or the cell is hidden. */
export function homeStats(data: HomeData) {
  const cards = [...(data.home?.vendors ?? []), ...(data.home?.brands ?? [])];
  return {
    verifiedVendors: cards.filter((c) => c.verification_status === "verified").length,
    coveredPincodes: data.coveredPincodes.length,
    sellers: data.home?.price_banner?.seller_count ?? 0,
    reviews: Object.values(data.ratings).reduce((sum, r) => sum + r.rating_count, 0),
  };
}
