const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export type LocalizedText = Record<string, string>;

export interface PublicBranch {
  id: string;
  business_id: string;
  address: string;
  state: string;
  district: string;
  pincode: string;
  // Backend serializes Decimal as JSON string on the wire
  lat: string | null;
  lng: string | null;
  hours: Record<string, unknown>;
}

export interface BusinessDetail {
  business: {
    id: string;
    name: string;
    slug: string;
    type: string;
    status: string;
    verification_status: string;
    subscription_tier: string;
    claimable: boolean;
    primary_pincode: string;
    description: LocalizedText | null;
    created_at: string;
  };
  branches: PublicBranch[];
  categories: { id: string; slug: string; name: LocalizedText }[];
  coverage_pincodes: string[];
}

export interface CatalogProduct {
  id: string;
  name: string;
  slug: string;
  specs: Record<string, unknown>;
  price_display: string | null;
  images: string[];
}

/** GET /directory/businesses/{slug}/nearby-branches (D27 Task 3, public).
 * lat/lng serialize as Decimal-wire-strings (D24 precedent). */
export type NearbyBranch = {
  id: string;
  address: string;
  district: string;
  state: string;
  pincode: string;
  lat: string | null;
  lng: string | null;
  distance_m: number;
};

export type RatingSummary = { rating_avg: string | null; rating_count: number };
export type ReviewItem = {
  id: string;
  rating: number;
  body: LocalizedText | null;
  created_at: string;
};

/** Server-side public read, direct to backend (mirrors web-agri's business
 * page): 404 -> null (notFound), 410 -> "gone" (suspended/disabled business,
 * M1.5 unavailable page - deliberately indistinguishable which), other
 * non-ok -> throw (real error). */
export async function fetchBusiness(slug: string): Promise<BusinessDetail | "gone" | null> {
  const res = await fetch(`${API}/directory/businesses/${encodeURIComponent(slug)}`, {
    next: { revalidate: 300 },
  });
  if (res.status === 410) return "gone";
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`directory fetch failed: ${res.status}`);
  return (await res.json()) as BusinessDetail;
}

/** Tolerant: a missing/failed catalog read degrades to an empty product list
 * rather than failing the whole profile render. */
export async function fetchProducts(slug: string): Promise<CatalogProduct[]> {
  try {
    const res = await fetch(
      `${API}/catalog/businesses/${encodeURIComponent(slug)}/products?limit=50`,
      { next: { revalidate: 300 } },
    );
    if (!res.ok) return [];
    return ((await res.json()) as { items: CatalogProduct[] }).items;
  } catch {
    return [];
  }
}

/** Public review reads — NOT via /api/reviews (that proxy is auth-required
 * by design and would 401 guests). Tolerant of non-ok responses. */
export async function fetchReviews(
  businessId: string,
): Promise<{ summary: RatingSummary; items: ReviewItem[] }> {
  const qs = `target_type=business&target_id=${businessId}`;
  const [summaryRes, listRes] = await Promise.all([
    fetch(`${API}/reviews/summary?${qs}`, { next: { revalidate: 300 } }),
    fetch(`${API}/reviews?${qs}&limit=10`, { next: { revalidate: 300 } }),
  ]);
  const summary: RatingSummary = summaryRes.ok
    ? ((await summaryRes.json()) as RatingSummary)
    : { rating_avg: null, rating_count: 0 };
  const items: ReviewItem[] = listRes.ok
    ? ((await listRes.json()) as { items: ReviewItem[] }).items
    : [];
  return { summary, items };
}
