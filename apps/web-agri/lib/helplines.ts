/**
 * A-U3 W2 — helplines from the E5 dataset.
 *
 * This file replaces `data/helplines.ts`, the static TS array A-U1
 * shipped "pending E5 migration". That file is DELETED, not kept as a
 * fallback: a second copy of a phone number is a second thing to keep
 * true, and the stale copy is the one that survives.
 *
 * Two things changed in the move, and both are the point of moving:
 *  - the display NAME is data now, not an i18n key, so a helpline added
 *    by an admin renders in three languages without a deploy;
 *  - `source` + `verified_on` are PER NUMBER rather than one stamp for
 *    the whole band, so a number nobody has re-checked says so.
 */
const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * A day. Helpline numbers change on the order of years, and the offline
 * page (D59) needs a copy the service worker can hold — so a long
 * revalidate is correct here, not a compromise.
 */
const REVALIDATE_SECONDS = 86_400;

export interface Helpline {
  slug: string;
  name: Record<string, string>;
  /** Exactly as the source prints it, e.g. "1800-180-1551". */
  number: string;
  /** Digits only, for tel:. */
  dial: string;
  scope: "national" | "state";
  state: string | null;
  source: string;
  source_url: string;
  verified_on: string;
}

/**
 * National helplines, plus `state`'s when one is known.
 *
 * `[]` on failure, and an empty band renders ABSENT — the honesty rule
 * applies to phone numbers more than to anything else on the page. A
 * band with no numbers helps nobody; a band with a wrong number is worse
 * than no band.
 */
export async function fetchHelplines(
  state?: string | null,
): Promise<Helpline[]> {
  const query = state ? `?state=${encodeURIComponent(state)}` : "";
  try {
    const res = await fetch(`${API}/market/helplines${query}`, {
      next: { revalidate: REVALIDATE_SECONDS },
    });
    if (!res.ok) return [];
    return (await res.json()) as Helpline[];
  } catch {
    return [];
  }
}

/** The band's footer stamp: the distinct sources, and the OLDEST
 * verification date across the numbers shown.
 *
 * Oldest, not newest, deliberately. The stamp is a claim about the whole
 * band, and the honest claim is the weakest one in it — showing the most
 * recent date would let one freshly-checked number vouch for three that
 * nobody has looked at in years. */
export function helplineStamp(helplines: Helpline[]): {
  sources: string;
  date: string;
} {
  const sources = [...new Set(helplines.map((h) => h.source))].join(" · ");
  const date = helplines.map((h) => h.verified_on).sort()[0] ?? "";
  return { sources, date };
}
