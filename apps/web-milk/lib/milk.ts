const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * Wire shapes for `GET /catalog/milk/home/{pincode}` (D23 Task 5) — mirror
 * `MilkHomeOut` in `backend/core/modules/directory/milk_home_schemas.py`
 * field-for-field, including nullability. Ground-truthed against the live
 * endpoint for all three scopes (covered / tn_no_vendors / out_of_area) —
 * `price_banner` is non-null ONLY for scope === "covered"; `location` is
 * null ONLY for scope === "out_of_area".
 */
export type MilkScope = "covered" | "tn_no_vendors" | "out_of_area";

export interface MilkProduct {
  milk_type: string | null;
  fat_percent: number | null;
  pack_size: string | null;
  price_display: string | null;
}

export interface MilkCard {
  id: string;
  name: string;
  slug: string;
  type: string;
  verification_status: string;
  subscription_tier: string;
  distance_m: number;
  lat: number | null;
  lng: number | null;
  products: MilkProduct[];
}

export interface PriceBand {
  milk_type: string;
  low: number;
  high: number;
  unit: string | null;
}

export interface MilkHome {
  scope: MilkScope;
  location: { pincode: string; district: string; state: string | null } | null;
  filters: string[];
  price_banner: { lines: PriceBand[]; seller_count: number } | null;
  vendors: MilkCard[];
  brands: MilkCard[];
  next_cursor: string | null;
}

/** Display metadata for a schema-driven milk_type KEY. The filter SET is
 * schema-driven (backend `filters` array); icon + vernacular are
 * presentation-only, keyed by the backend value with a graceful fallback
 * for unknown future keys. */
export const MILK_TYPE_META: Record<string, { en: string; vern: string; icon: string }> = {
  all: { en: "All", vern: "எல்லாம்", icon: "🥛" },
  cow: { en: "Cow", vern: "பசு", icon: "🐄" },
  buffalo: { en: "Buffalo", vern: "எருமை", icon: "🐃" },
  a2: { en: "A2", vern: "", icon: "✨" },
  toned: { en: "Toned", vern: "", icon: "🥛" },
  organic: { en: "Organic", vern: "", icon: "🌿" },
};

export function milkTypeMeta(key: string) {
  return MILK_TYPE_META[key] ?? { en: key, vern: "", icon: "🥛" };
}

/** "Cow ₹52–60/1l · Buffalo ₹68 · 2 sellers found" from real listings.
 * Collapses low === high to a single price and only appends a unit
 * suffix when `unit` is non-null. */
export function priceBannerText(banner: NonNullable<MilkHome["price_banner"]>): string {
  const parts = banner.lines.map((b) => {
    const range = b.low === b.high ? `₹${b.low}` : `₹${b.low}–${b.high}`;
    const unit = b.unit ? `/${b.unit}` : "";
    return `${milkTypeMeta(b.milk_type).en} ${range}${unit}`;
  });
  const sellerText = `${banner.seller_count} ${banner.seller_count === 1 ? "seller" : "sellers"} found`;
  return parts.length > 0 ? `${parts.join(" · ")} · ${sellerText}` : sellerText;
}

export interface CoveredPincode {
  pincode: string;
  district: string;
}

/** Sitemap feed (D28) — `GET /catalog/milk/coverage/pincodes`. Null on
 * failure so sitemap generation degrades to static entries instead of
 * failing the build (CI builds run with no backend). */
export async function fetchCoveredPincodes(
  cursor?: string,
): Promise<{ items: CoveredPincode[]; next_cursor: string | null } | null> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  try {
    const res = await fetch(`${API}/catalog/milk/coverage/pincodes${qs}`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    return (await res.json()) as { items: CoveredPincode[]; next_cursor: string | null };
  } catch {
    return null;
  }
}

/** Server-side public read — direct to backend (NOT the BFF proxy), with
 * `next: { revalidate: 300 }` for ISR. Returns null on any non-ok response
 * or thrown error so the page can degrade gracefully instead of crashing. */
export async function fetchMilkHome(pincode: string, type?: string): Promise<MilkHome | null> {
  const qs = type && type !== "all" ? `?type=${encodeURIComponent(type)}` : "";
  try {
    const res = await fetch(`${API}/catalog/milk/home/${encodeURIComponent(pincode)}${qs}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return (await res.json()) as MilkHome;
  } catch {
    return null;
  }
}
