/**
 * `agri_loc` — client-managed location cookie (D19). Unlike auth-client's
 * sealed session cookies, this one is deliberately plain: URL-encoded JSON
 * that both the browser and SSR can read directly, and that must NEVER be
 * mistaken for a JWT/JWE (the e2e storage scan fails on `/eyJ[\w-]{10,}/`).
 * Keep this file `document`-free — it is unit-tested under plain node.
 */
export const LOC_COOKIE = "agri_loc";

export type LocSource = "profile" | "gps" | "pincode" | "ip" | "none";

const SOURCES: ReadonlySet<string> = new Set<LocSource>([
  "profile",
  "gps",
  "pincode",
  "ip",
  "none",
]);

export interface LocContext {
  pincode: string | null;
  district: string | null;
  state: string | null;
  source: LocSource;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

/**
 * `cookieValue` is the raw (still URL-encoded) cookie value — i.e. whatever
 * sits after `agri_loc=` in `document.cookie` or a `Cookie` header. Returns
 * `null` on anything malformed rather than throwing, so callers can always
 * treat a missing/bad cookie the same as "no location known yet".
 */
export function parseLocCookie(cookieValue: string | undefined): LocContext | null {
  if (!cookieValue) return null;

  let raw: unknown;
  try {
    raw = JSON.parse(decodeURIComponent(cookieValue));
  } catch {
    return null;
  }

  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const obj = raw as Record<string, unknown>;
  const { p, d, s, src } = obj;

  if (!("p" in obj) || !("d" in obj) || !("s" in obj) || !("src" in obj)) return null;
  if (!isNullableString(p) || !isNullableString(d) || !isNullableString(s)) return null;
  if (typeof src !== "string" || !SOURCES.has(src)) return null;

  return { pincode: p, district: d, state: s, source: src as LocSource };
}

/** Full `Set-Cookie`-ready string: `agri_loc=%7B...%7D; Path=/; Max-Age=...; SameSite=Lax`. */
export function serializeLocCookie(loc: LocContext): string {
  const payload = { p: loc.pincode, d: loc.district, s: loc.state, src: loc.source };
  const value = encodeURIComponent(JSON.stringify(payload));
  return [`${LOC_COOKIE}=${value}`, "Path=/", "Max-Age=31536000", "SameSite=Lax"].join("; ");
}

/**
 * "District · 641001" / "District" / "State" / null — never shows a bare
 * pincode with no place name, and never shows anything for `loc === null`.
 */
export function locLabel(loc: LocContext | null): string | null {
  if (!loc) return null;
  if (loc.district && loc.pincode) return `${loc.district} · ${loc.pincode}`;
  if (loc.district) return loc.district;
  if (loc.state) return loc.state;
  return null;
}
