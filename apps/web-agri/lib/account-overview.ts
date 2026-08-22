/**
 * The overview's reads (AG-U5 P2).
 *
 * Five endpoints, in parallel, every one of them already shipped:
 *   /leads/mine          — enquiries this person sent
 *   /leads/needs/mine    — needs they broadcast, with each routed business
 *   /market/alerts       — their mandi digest subscriptions
 *   /content/bookmarks   — saved items
 *   /coins/balance       — one wallet, one number
 *
 * COUNTS ARE HONEST, NOT EXACT, AND THAT IS DELIBERATE. None of these
 * endpoints returns a total — they are cursor-paginated, because every list
 * in this repo is. So a "count" is really "how many came back in one page",
 * and when a page comes back full the tile says `20+` rather than inventing a
 * total nobody asked the database for. The A5 reference draws bare numbers;
 * it was drawn against mock data where the number was known.
 *
 * Every read fails SOFT and independently. One dead endpoint costs its own
 * tile, never the page — the same rule the home's sections follow.
 */

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** One page. Beyond this a tile says "N+" instead of a total. */
export const PAGE = 20;

export interface InquiryLike {
  id?: string;
  status: string;
  /** Free-form by design: a milk enquiry and a seed enquiry carry different
   * fields, so the panel reads a message out of it rather than a schema. */
  payload?: Record<string, unknown>;
  responses: { id: string }[];
}

export interface NeedRouteLike {
  responses: { id: string }[];
}

export interface NeedLike {
  id?: string;
  status: string;
  payload?: Record<string, unknown>;
  routes: NeedRouteLike[];
}

export interface AlertLike {
  id: string;
  pincode: string;
  last_notified_on: string | null;
}

export interface SavedLike {
  slug?: string;
  title?: string;
  kind?: string;
}

export interface OverviewCounts {
  /** Open enquiries plus open needs — what the panel below the tile lists. */
  activeThreads: number;
  /** Businesses that actually replied, across both. */
  replies: number;
  alerts: number;
  saved: number;
  /** `null` when the balance could not be read. Not zero — see below. */
  coins: number | null;
}

/** Statuses that mean "this is still going". Everything else is finished. */
const ACTIVE_INQUIRY = new Set(["new", "responded"]);
const ACTIVE_NEED = new Set(["open"]);

/** Replies to a need, summed across every business it was routed to. */
export function quotesFor(need: NeedLike): number {
  return need.routes.reduce((total, route) => total + route.responses.length, 0);
}

export function deriveCounts(input: {
  inquiries: InquiryLike[];
  needs: NeedLike[];
  alerts: AlertLike[];
  saved: SavedLike[];
  /** `null` when /coins/balance could not be read. */
  balance: number | null;
}): OverviewCounts {
  const activeThreads =
    input.inquiries.filter((i) => ACTIVE_INQUIRY.has(i.status)).length +
    input.needs.filter((n) => ACTIVE_NEED.has(n.status)).length;
  const replies =
    input.inquiries.reduce((total, i) => total + i.responses.length, 0) +
    input.needs.reduce((total, n) => total + quotesFor(n), 0);
  return {
    activeThreads,
    replies,
    alerts: input.alerts.length,
    saved: input.saved.length,
    // Passed through, INCLUDING null. "We could not read your balance" and
    // "your balance is zero" are different claims and only one of them is
    // safe to print as a number.
    coins: input.balance,
  };
}

/**
 * How a count renders.
 *
 * A full page means there may be more, so the number gets a `+`. Zero never
 * does — "0+" is noise, and an empty list is genuinely empty whether or not
 * a cursor existed.
 */
export function countLabel(value: number, capped: boolean): string {
  if (value === 0) return "0";
  return capped ? `${value}+` : `${value}`;
}

export interface OverviewData {
  inquiries: InquiryLike[];
  inquiriesCapped: boolean;
  needs: NeedLike[];
  needsCapped: boolean;
  alerts: AlertLike[];
  saved: SavedLike[];
  savedCapped: boolean;
  balance: number | null;
  counts: OverviewCounts;
}

async function readList<T>(url: string, token: string): Promise<{ items: T[]; capped: boolean }> {
  try {
    const res = await fetch(url, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return { items: [], capped: false };
    const body = (await res.json()) as { items?: T[]; next_cursor?: string | null };
    const items = body.items ?? [];
    return { items, capped: Boolean(body.next_cursor) };
  } catch {
    return { items: [], capped: false };
  }
}

export async function fetchOverview(token: string): Promise<OverviewData> {
  const headers = { authorization: `Bearer ${token}` };
  const [inquiries, needs, alerts, saved, balance] = await Promise.all([
    readList<InquiryLike>(`${API}/leads/mine?limit=${PAGE}`, token),
    readList<NeedLike>(`${API}/leads/needs/mine?limit=${PAGE}`, token),
    // /market/alerts returns a bare array, not a page: alerts are capped per
    // user server-side, so there is nothing to paginate.
    (async (): Promise<AlertLike[]> => {
      try {
        const res = await fetch(`${API}/market/alerts`, { headers, cache: "no-store" });
        return res.ok ? ((await res.json()) as AlertLike[]) : [];
      } catch {
        return [];
      }
    })(),
    readList<SavedLike>(`${API}/content/bookmarks?limit=${PAGE}`, token),
    (async (): Promise<number | null> => {
      try {
        const res = await fetch(`${API}/coins/balance`, { headers, cache: "no-store" });
        if (!res.ok) return null;
        const body = (await res.json()) as { balance?: number };
        return typeof body.balance === "number" ? body.balance : null;
      } catch {
        return null;
      }
    })(),
  ]);
  return {
    inquiries: inquiries.items,
    inquiriesCapped: inquiries.capped,
    needs: needs.items,
    needsCapped: needs.capped,
    alerts,
    saved: saved.items,
    savedCapped: saved.capped,
    balance,
    counts: deriveCounts({
      inquiries: inquiries.items,
      needs: needs.items,
      alerts,
      saved: saved.items,
      balance,
    }),
  };
}
