/**
 * A-U4b O11 (AG-A69) — the "Live on agri.in" activity feed.
 *
 * ONE public read: `GET /directory/feed/live` — real platform events only
 * (need posted, business joined, review approved, lead sent), newest-first,
 * last-24h window, ~30 rows max. The endpoint is gated by the
 * `agri_live_feed` flag, which is OFF at D57: while OFF it 404s
 * (`feature_disabled`), the fetch below returns null, and the section is
 * ABSENT from the DOM — the exact market/today degrade path (F1 rule: a
 * dead or dark engine never 500s the home, and events are NEVER fabricated
 * to fill the gap).
 *
 * The phrase-building half of this file is pure (kind + payload fields →
 * message key + ICU args, or null meaning "skip this item"), so the honesty
 * rules — never render an empty phrase, never pad, never recycle — are unit
 * tested without a render.
 */

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export type LiveFeedKind =
  | "need_posted"
  | "business_joined"
  | "review_approved"
  | "lead_sent";

/** Wire shape of one feed row — mirrors the O11 backend contract
 * field-for-field. Every field except `kind`/`occurred_at` is nullable:
 * a phrase renders ONLY from the fields its kind actually has. */
export interface LiveFeedItem {
  kind: LiveFeedKind;
  /** ISO timestamp. Fetched but never rendered — see `phraseFor`. */
  occurred_at: string;
  district: string | null;
  state: string | null;
  business_name: string | null;
  business_slug: string | null;
  rating: number | null;
}

export interface LiveFeedPayload {
  items: LiveFeedItem[];
}

/**
 * The feed read, house style (`lib/home.ts` getJson): any non-OK status —
 * including the flag-off 404 — and any network failure degrade to null.
 * Null means the section is absent; the flag-off state costs one cached
 * 404 per window and nothing else. The revalidate window is the CALLER's
 * declaration — the home passes it from `lib/home-data.ts`, where every
 * read's window lives together.
 */
export async function fetchLiveFeed(
  opts: { revalidate?: number } = {},
): Promise<LiveFeedPayload | null> {
  const revalidate = opts.revalidate ?? 300;
  try {
    const res = await fetch(`${API}/directory/feed/live`, {
      next: { revalidate },
    });
    if (!res.ok) return null;
    const body = (await res.json()) as LiveFeedPayload;
    if (typeof body !== "object" || body === null || !Array.isArray(body.items)) {
      return null;
    }
    return body;
  } catch {
    return null;
  }
}

/** ui.agriHome.liveFeed.* message key + its ICU args, for one phrase. */
export interface LiveFeedPhrase {
  key: "needPosted" | "businessJoined" | "reviewApproved" | "leadSent";
  args: Record<string, string | number>;
}

/**
 * One feed row → the localized phrase it earns, or null meaning SKIP.
 *
 * Skip rules (the "never render an empty phrase" contract):
 *  - business_joined / lead_sent without a business_name would render bare
 *    ("… joined agri.in" / "A farmer contacted …") — skipped;
 *  - review_approved with neither business_name nor rating is just the
 *    words "New review", which says nothing — skipped;
 *  - an unknown kind (a future backend event type) is skipped rather than
 *    crashed on, so the feed can grow without a lockstep deploy.
 *
 * need_posted always renders: "a need was posted" is a complete, true
 * sentence with or without its district.
 *
 * NO timestamp ever reaches a phrase. `occurred_at` is on the wire, but the
 * page is cached (5-minute declared window plus ISR realities), so a
 * relative "2 min ago" baked into cached HTML lies within minutes of being
 * rendered — the mandi ISR-today lesson (A-U4 O1: cached pages must not
 * imply a freshness they don't have). The section label says "recent
 * activity" instead, which stays true for the whole cache window. NO counts
 * either: an unmeasured count is the reference mockup's fabrication.
 */
export function phraseFor(item: LiveFeedItem): LiveFeedPhrase | null {
  switch (item.kind) {
    case "need_posted":
      return {
        key: "needPosted",
        args: {
          hasDistrict: item.district ? "yes" : "no",
          district: item.district ?? "",
        },
      };
    case "business_joined":
      if (!item.business_name) return null;
      return { key: "businessJoined", args: { name: item.business_name } };
    case "review_approved":
      if (!item.business_name && item.rating === null) return null;
      return {
        key: "reviewApproved",
        args: {
          hasName: item.business_name ? "yes" : "no",
          name: item.business_name ?? "",
          hasRating: item.rating !== null ? "yes" : "no",
          rating: item.rating ?? 0,
        },
      };
    case "lead_sent":
      if (!item.business_name) return null;
      return { key: "leadSent", args: { name: item.business_name } };
    default:
      return null;
  }
}

/**
 * The whole payload → renderable phrases. `[]` for a null payload (flag
 * off / engine down), an empty feed, or a feed whose every row was skipped
 * — and `[]` means the section is ABSENT (EMPTY MEANS ABSENT: the strip is
 * never recycled from older events, never padded with invented ones).
 */
export function phrasesFor(feed: LiveFeedPayload | null): LiveFeedPhrase[] {
  if (!feed) return [];
  return feed.items
    .map(phraseFor)
    .filter((p): p is LiveFeedPhrase => p !== null);
}
