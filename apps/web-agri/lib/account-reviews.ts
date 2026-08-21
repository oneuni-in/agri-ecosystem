/**
 * The author's own reviews (AG-U5 P4).
 *
 * Reads `GET /reviews/mine`, which was added for this page: a review is
 * `pending` on write and therefore absent from every public list, and
 * `GET /reviews` is keyed by target rather than author — so before this there
 * was nowhere on the platform that could answer "where did my review go?".
 */

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export interface MyReview {
  id: string;
  target_type: string;
  target_id: string;
  target_name: string | null;
  target_slug: string | null;
  rating: number;
  body: Record<string, string> | null;
  moderation_status: string;
  created_at: string;
}

export interface StatusTone {
  /** The `ui.account.reviewsPage.*` key for the chip's label. */
  key: "published" | "pending" | "rejected";
  className: string;
}

/**
 * The chip beside a review.
 *
 * An unrecognised status reads as "in moderation", deliberately. If the enum
 * grows a value this build has not seen, the safe answer is "not live yet" —
 * telling someone their words are public when they may not be is the only
 * one of these mistakes that has a consequence.
 */
export function statusTone(status: string): StatusTone {
  if (status === "approved") {
    return { key: "published", className: "bg-verified-bg text-verified-fg" };
  }
  if (status === "rejected") {
    return { key: "rejected", className: "bg-line text-sub" };
  }
  return { key: "pending", className: "bg-sponsored-bg text-sponsored-fg" };
}

/**
 * The review's text in the reader's language, or any language it has.
 *
 * The fallback is deliberate: these are the author's own words, and hiding
 * them because the interface happens to be in Hindi today would be worse than
 * showing the Tamil they were written in. `null` only when there is genuinely
 * no text — a rating with no body is legal.
 */
export function pickBody(body: Record<string, string> | null, locale: string): string | null {
  if (!body) return null;
  const preferred = body[locale];
  if (preferred) return preferred;
  return Object.values(body).find((value) => Boolean(value)) ?? null;
}

/**
 * `null` means "could not read", which is NOT the same as "you have no
 * reviews" — and the difference matters more here than almost anywhere else
 * on the dashboard. Falling back to an empty array would render "You have not
 * written a review yet" at someone who has, which is both false and
 * upsetting: the page exists precisely to reassure people their words did not
 * vanish. The caller renders a "cannot load" notice instead.
 */
export async function fetchMyReviews(token: string, limit = 20): Promise<MyReview[] | null> {
  try {
    const res = await fetch(`${API}/reviews/mine?limit=${limit}`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { items?: MyReview[] };
    return body.items ?? [];
  } catch {
    return null;
  }
}
