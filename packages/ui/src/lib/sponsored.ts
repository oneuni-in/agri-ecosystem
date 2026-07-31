/**
 * Served-ad payload guard (D21). The backend re-validates target_url at
 * serve time; this is the client-side half of the same ad-as-XSS gate, plus
 * the labeling contract: a payload without label === "sponsored" is not an
 * ad we will render (unlabeled ads are forbidden - UX law 5).
 * Keep this file document-free - unit-tested under plain node.
 */
export interface ServedAd {
  placement_id: string;
  creative_id: string;
  slot_key: string;
  label: "sponsored";
  title: string;
  body: string;
  media_urls: string[];
  target_url: string;
}

export function isSafeTargetUrl(url: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(url); // relative/scheme-relative throw -> false
  } catch {
    return false;
  }
  return parsed.protocol === "http:" || parsed.protocol === "https:";
}

export function parseServedAd(raw: unknown): ServedAd | null {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const obj = raw as Record<string, unknown>;
  const strings = ["placement_id", "creative_id", "slot_key", "title", "body", "target_url"];
  if (!strings.every((k) => typeof obj[k] === "string")) return null;
  if (obj.label !== "sponsored") return null;
  if (!Array.isArray(obj.media_urls) || !obj.media_urls.every((u) => typeof u === "string"))
    return null;
  if (!isSafeTargetUrl(obj.target_url as string)) return null;
  return obj as unknown as ServedAd;
}

/** Media URLs get the same http(s)-absolute-only gate as target_url (M2:
 * img-only creatives, no HTML - an unsafe src renders nothing). */
export function isSafeMediaUrl(url: string): boolean {
  return isSafeTargetUrl(url);
}

/** M2 serve envelope: prefer `ads` (carousel), fall back to legacy `ad`.
 * Unlabeled/unsafe entries are dropped; unsafe media URLs are stripped
 * from surviving ads. */
export function parseServeResponse(raw: unknown): ServedAd[] {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return [];
  const obj = raw as Record<string, unknown>;
  const list = Array.isArray(obj.ads) && obj.ads.length > 0 ? obj.ads : [obj.ad];
  const out: ServedAd[] = [];
  for (const entry of list) {
    const ad = parseServedAd(entry);
    if (ad) out.push({ ...ad, media_urls: ad.media_urls.filter(isSafeMediaUrl) });
  }
  return out;
}

/** M3.B sponsored-listing injection — page positions 1 and 6 (0-indexed
 * display slots 0 and 5), max 2 per page (spec item 6). */
export const SPONSORED_POSITIONS: readonly number[] = [0, 5];
export const MAX_SPONSORED_PER_PAGE = 2;

export type ListEntry<T> = { kind: "organic"; item: T } | { kind: "sponsored"; ad: ServedAd };

/** Render-layer injection (M3.B / NN3): the organic array is NEVER
 * reordered, filtered or re-counted — sponsored entries are spliced into the
 * RENDERED flow only, so the cursor stream (built from organic items) is
 * byte-identical with sponsorship on or off. Empty organic list ⇒ nothing is
 * injected (no ad-only pages); positions past the end clamp to the end. */
export function injectSponsored<T>(
  organic: readonly T[],
  ads: readonly ServedAd[],
  positions: readonly number[] = SPONSORED_POSITIONS,
): ListEntry<T>[] {
  const out: ListEntry<T>[] = organic.map((item) => ({ kind: "organic", item }));
  if (out.length === 0) return out;
  ads.slice(0, MAX_SPONSORED_PER_PAGE).forEach((ad, i) => {
    const pos = positions[i];
    if (pos === undefined) return;
    out.splice(Math.min(pos, out.length), 0, { kind: "sponsored", ad });
  });
  return out;
}

const PINCODE_RE = /^\d{6}$/;
const CATEGORY_RE = /^[a-z0-9-]{1,40}$/;
const SERVE_LOCALES: ReadonlySet<string> = new Set(["en", "ta", "hi"]);
const MAX_SERVE_COUNT = 5;

export interface AdServeContext {
  pincode?: string | null | undefined;
  category?: string | null | undefined;
  count?: number | undefined;
  locale?: string | undefined;
}

/** Query string for `GET /ads/serve` — malformed context is dropped
 * client-side rather than round-tripping to a 422. */
export function serveQuery(slotKey: string, ctx: AdServeContext = {}): string {
  const q = new URLSearchParams({ slot: slotKey });
  if (ctx.pincode && PINCODE_RE.test(ctx.pincode)) q.set("pincode", ctx.pincode);
  if (ctx.category && CATEGORY_RE.test(ctx.category)) q.set("category", ctx.category);
  if (ctx.count && ctx.count > 1) q.set("count", String(Math.min(ctx.count, MAX_SERVE_COUNT)));
  if (ctx.locale && SERVE_LOCALES.has(ctx.locale)) q.set("locale", ctx.locale);
  return q.toString();
}
