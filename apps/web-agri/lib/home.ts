import type { TodayPayload } from "@agri/types";
import { parseLocCookie } from "@agri/ui";

import { DEFAULT_LOCATION } from "./default-location";

/**
 * A-U1 CP2 — the agri.in home's server-side data layer, ported from
 * web-milk's `lib/home.ts` (the proven U1 engine-binding pattern).
 *
 * Every fetch here is server-side, public-read, and swallows failure into
 * `null`/`[]`: a dead engine never 500s the home (F1 rule), the section it
 * feeds is simply absent from the DOM.
 */
const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * The visitor's pincode for this render: their `agri_loc` cookie (D19 — set
 * by the header pill / GPS) falling back to `DEFAULT_LOCATION`. Reading the
 * cookie is what makes the home render "based on the header pincode", and
 * what makes the route dynamic.
 */
export function resolveHomePincode(cookieValue: string | undefined): string {
  return parseLocCookie(cookieValue)?.pincode ?? DEFAULT_LOCATION.pincode;
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

/* ── §6 · vertical registry ────────────────────────────────────────────── */

/** The 5 A1 groups, in section order. */
export const VERTICAL_GROUPS = [
  "essentials",
  "inputs",
  "services",
  "community",
  "buy-sell",
] as const;
export type VerticalGroupKey = (typeof VERTICAL_GROUPS)[number];

export interface VerticalItem {
  slug: string;
  /** TranslatedString {en, ta, hi} from the registry. */
  name: Record<string, string>;
  group: VerticalGroupKey;
  order: number;
  icon: string;
  soon: boolean;
}

interface VerticalWire {
  slug: string;
  name: Record<string, string>;
  engines_enabled: Record<string, unknown>;
  nav_placement: Record<string, unknown>;
}

function parsePlacement(v: VerticalWire): VerticalItem | null {
  const home = (v.nav_placement ?? {})["agri_home"] as
    | { group?: unknown; order?: unknown; icon?: unknown; soon?: unknown }
    | undefined;
  if (!home || typeof home.group !== "string") return null;
  if (!(VERTICAL_GROUPS as readonly string[]).includes(home.group)) return null;
  return {
    slug: v.slug,
    name: v.name ?? {},
    group: home.group as VerticalGroupKey,
    order: typeof home.order === "number" ? home.order : 0,
    icon: typeof home.icon === "string" ? home.icon : "🌾",
    soon: home.soon === true,
  };
}

/**
 * §6 — the category grid's ONE source: `GET /catalog/verticals` (D17 public
 * registry read, cursor-paginated, limit ≤ 50). The grid renders exactly
 * what the registry contains — zero hardcoded category lists in app code.
 * The cursor walk is bounded (5 pages ≫ the 36-entry registry) so a runaway
 * table can never hang the home.
 */
export async function fetchVerticals(): Promise<VerticalItem[]> {
  const out: VerticalItem[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < 5; page++) {
    const qs: string = cursor ? `?cursor=${encodeURIComponent(cursor)}&limit=50` : "?limit=50";
    const body = await getJson<{ items: VerticalWire[]; next_cursor: string | null }>(
      `/catalog/verticals${qs}`,
      3600,
    );
    if (!body) break;
    for (const item of body.items) {
      const parsed = parsePlacement(item);
      // Verticals without an agri_home placement (e.g. milk's own registry
      // entries) simply do not belong on this grid.
      if (parsed) out.push(parsed);
    }
    if (!body.next_cursor) break;
    cursor = body.next_cursor;
  }
  return out;
}

/** §6/A2 — A1 `.vg-dot` colour per group + the tile icon-disc tint. ONE
 * binding for the home grid and /categories (identical tiles, both pages). */
export const GROUP_STYLE: Record<
  VerticalGroupKey,
  { dot: string; tint: "green" | "sand" | "aqua" | "lilac" | "peach" }
> = {
  essentials: { dot: "bg-brand-deep", tint: "green" },
  inputs: { dot: "bg-coins-fg", tint: "sand" },
  services: { dot: "bg-down", tint: "aqua" },
  community: { dot: "bg-brand", tint: "lilac" },
  "buy-sell": { dot: "bg-sponsored-fg", tint: "peach" },
};

/** A2 — stage letter per non-live group (blueprint stages B–E). This is
 * presentation config about the ROLLOUT PLAN, not a category list — tiles
 * and landings still render only what the registry returns. */
export const GROUP_STAGE: Partial<Record<VerticalGroupKey, string>> = {
  inputs: "B",
  services: "C",
  community: "D",
  "buy-sell": "E",
};

/** Group key → ui.agriHome.categories.groups.* message key. */
export const GROUP_LABEL_KEY: Record<VerticalGroupKey, string> = {
  essentials: "essentials",
  inputs: "inputs",
  services: "services",
  community: "community",
  "buy-sell": "buySell",
};

/** Groups in A1 order (essentials → inputs → services → community →
 * buy-sell), items by their registry `order`. */
export function groupVerticals(
  items: VerticalItem[],
): { key: VerticalGroupKey; items: VerticalItem[] }[] {
  return VERTICAL_GROUPS.map((key) => ({
    key,
    items: items.filter((v) => v.group === key).sort((a, b) => a.order - b.order),
  })).filter((group) => group.items.length > 0);
}

/* ── §10 · directory row ───────────────────────────────────────────────── */

/**
 * Wire shape for `GET /directory/covers/{pincode}` — mirrors `CoversItemOut`
 * field-for-field (same type web-milk's `lib/directory.ts` documents).
 * `distance_m` uses the backend's `UNLOCATABLE_M = 1_000_000_000` sentinel;
 * callers must treat values >= that as "no distance".
 */
export interface DirectoryCard {
  id: string;
  name: string;
  slug: string;
  type: string;
  verification_status: string;
  subscription_tier: string;
  primary_pincode: string;
  distance_m: number;
  lat: string | null;
  lng: string | null;
}

export const UNLOCATABLE_M = 1_000_000_000;

/**
 * §10 — "agri businesses near you": the first 3 businesses covering the
 * visitor's pincode, nearest first, from the SAME public covers() read the
 * milk home and both directory surfaces use. No category filter: agri.in is
 * the hub, so every covering business qualifies.
 */
export async function fetchDirectoryRow(pincode: string): Promise<DirectoryCard[]> {
  const body = await getJson<{ items: DirectoryCard[]; next_cursor: string | null }>(
    `/directory/covers/${encodeURIComponent(pincode)}?limit=3`,
  );
  return body?.items ?? [];
}

/* ── §10/§15 · review signals (ported from milk) ───────────────────────── */

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

/**
 * The D18 review signals for a set of cards: per-business `/reviews/summary`
 * aggregates (rating + count) and, when `reviewsPerCard > 0`, the approved
 * review bodies themselves. ONE code path for every surface (milk's U1b
 * seam, ported verbatim). Approved-only comes from the engine itself, which
 * only ever returns approved rows to a public caller.
 */
export async function fetchReviewSignals(
  cards: { id: string; name: string; slug: string }[],
  reviewsPerCard = 0,
): Promise<{ ratings: Record<string, RatingSummary>; reviews: ReviewItem[] }> {
  const ratings: Record<string, RatingSummary> = {};
  const reviews: ReviewItem[] = [];

  const unique = [...new Map(cards.map((card) => [card.id, card])).values()];

  const perCard = await Promise.all(
    unique.map(async (card) => {
      const query = `target_type=business&target_id=${encodeURIComponent(card.id)}`;
      const [summary, list] = await Promise.all([
        getJson<RatingSummary>(`/reviews/summary?${query}`),
        reviewsPerCard > 0
          ? getJson<{ items: { id: string; rating: number; body: Record<string, string> }[] }>(
              `/reviews?${query}&limit=${reviewsPerCard}`,
            )
          : Promise.resolve(null),
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

  // Highest-rated first, stable id tiebreak, at most one review per business
  // (milk's §8d lesson: a single well-reviewed business must not own the
  // whole strip).
  reviews.sort((a, b) => b.rating - a.rating || a.id.localeCompare(b.id));
  const seen = new Set<string>();
  const distinct = reviews.filter((review) => {
    if (seen.has(review.business.slug)) return false;
    seen.add(review.business.slug);
    return true;
  });

  return { ratings, reviews: distinct };
}

/* ── §2b/§3/§6b/§7/§7b/§8/§9 · TODAY payload ───────────────────────────── */

/**
 * The `agri_today` flag is consumed at the API boundary: the W3 stub
 * endpoint `GET /market/today/{pincode}` 404s (`feature_disabled`) while the
 * flag is OFF, and this returns null — null means the severe strip, TODAY
 * strip, mandi ticker/cards, calendar, weather and schemes sections are
 * ABSENT from the DOM (assert node count, not visibility — the A11 lesson).
 * Flag ON: the deterministic fixture payload arrives in the frozen A-U2
 * contract shape (`TodayPayload` in @agri/types, mirror of the backend's
 * market_data/schemas.py) — A-U2's real workers replace the fixtures
 * WITHOUT this function or the UI changing.
 *
 * `cache: "no-store"`: the payload is per-pincode and time-of-day data; a
 * cached "today" is yesterday's lie. Any non-OK status, network failure or
 * shape mismatch degrades to null (F1 rule — a dead engine never 500s the
 * home).
 */
export async function fetchToday(pincode: string): Promise<TodayPayload | null> {
  try {
    const res = await fetch(`${API}/market/today/${encodeURIComponent(pincode)}`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const body = (await res.json()) as TodayPayload;
    // Minimal shape guard: the two blocks every flag-on section hangs off.
    if (typeof body !== "object" || body === null || !body.weather || !body.mandi) return null;
    return body;
  } catch {
    return null;
  }
}
