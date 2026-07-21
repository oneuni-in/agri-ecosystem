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
