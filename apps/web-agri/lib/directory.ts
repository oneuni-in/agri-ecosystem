/**
 * A-U3 W3 — the hub directory and search-results data layer.
 *
 * Both surfaces reuse engines that already exist. `/search` is the D19
 * facade (Meilisearch behind it), `/directory/covers/{pincode}` is E1's
 * nearest-first coverage read. This pass adds NO search engine and NO
 * directory engine — the build prompt is explicit about that, and the
 * only new code here is the fetching and the two pages.
 *
 * Same failure contract as every other lib in this app: server-side,
 * public-read, failure collapses to an empty result. A dead engine costs
 * the section, never the page.
 */
import { UNLOCATABLE_M } from "./home";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** Search is a query, not a page — a stale hit list is worse than a
 * slightly slower one, and results are per-query anyway. */
const SEARCH_REVALIDATE = 60;
/** Coverage changes when a business edits its area. Five minutes matches
 * the home's directory row. */
const DIRECTORY_REVALIDATE = 300;

export interface SearchHit {
  id: string;
  kind: "business" | "product";
  name: string;
  slug: string;
  /** Set on products: the business that sells it. */
  business_name: string | null;
  business_slug: string | null;
  description: Record<string, string> | null;
  categories: string[] | null;
  vertical: string | null;
  district: string | null;
  state: string | null;
  verified: boolean;
  price_display: string | null;
}

export interface SearchPage {
  items: SearchHit[];
  next_cursor: string | null;
}

export interface CoverageItem {
  id: string;
  name: string;
  slug: string;
  type: string;
  verification_status: string;
  subscription_tier: string;
  primary_pincode: string;
  /** Metres from the pincode centroid; UNLOCATABLE_M means "no location". */
  distance_m: number;
  lat: string | null;
  lng: string | null;
  /**
   * The branch a Call/WhatsApp tap on a card should reveal, or null when no
   * branch on this business carries a number.
   *
   * An ID, never a number. `/directory/covers` still returns no phone or
   * WhatsApp: only `POST /directory/branches/{id}/reveal` does, and that is
   * login-gated, daily-capped and DPDP-logged (D18.C). Putting the id in the
   * list payload moves the BUTTON to the card; it does not move the number.
   */
  contact_branch_id?: string | null;
  /**
   * The M3.C organic label, scored by the backend's `recommended.py` — the
   * SAME ranking milk.in's rail uses (verification, approved-review ratings,
   * lead first-response time, coverage freshness). Paid signals never enter
   * it, which is why this is a distinct field from `subscription_tier` and
   * why the badge must never be styled like the Sponsored pill.
   *
   * Optional on the wire: the flag defaults false server-side, so an older
   * payload simply means "no badge" rather than a parse failure.
   */
  recommended?: boolean;
}

export interface CoveragePage {
  items: CoverageItem[];
  next_cursor: string | null;
}

export interface ActiveCategory {
  id: string;
  slug: string;
  name: Record<string, string>;
  sort_order: number;
  /** Businesses in this category — the count the chips render. */
  business_count: number;
}

async function getJson<T>(path: string, revalidate: number): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, { next: { revalidate } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/**
 * The federated search the home band posts to.
 *
 * `site=agri` is fixed here, not a caller choice: this app is agri.in,
 * and a query string that could switch sites would let a crafted URL
 * show milk.in's index under agri.in's chrome.
 */
export async function searchAgri(options: {
  q: string;
  pincode?: string | undefined;
  kind?: "business" | "product" | undefined;
  cursor?: string | undefined;
  limit?: number | undefined;
}): Promise<SearchPage> {
  const params = new URLSearchParams({ site: "agri", q: options.q });
  if (options.pincode) params.set("pincode", options.pincode);
  if (options.kind) params.set("kind", options.kind);
  if (options.cursor) params.set("cursor", options.cursor);
  params.set("limit", String(options.limit ?? 20));
  return (
    (await getJson<SearchPage>(`/search?${params}`, SEARCH_REVALIDATE)) ?? {
      items: [],
      next_cursor: null,
    }
  );
}

/** Businesses covering a pincode, nearest first, optionally one category.
 * The SAME E1 read the home's §10 row uses. */
export async function fetchCoverage(options: {
  pincode: string;
  category?: string | undefined;
  cursor?: string | undefined;
  limit?: number | undefined;
}): Promise<CoveragePage> {
  const params = new URLSearchParams();
  if (options.category) params.set("category", options.category);
  if (options.cursor) params.set("cursor", options.cursor);
  params.set("limit", String(options.limit ?? 24));
  return (
    (await getJson<CoveragePage>(
      `/directory/covers/${encodeURIComponent(options.pincode)}?${params}`,
      DIRECTORY_REVALIDATE,
    )) ?? { items: [], next_cursor: null }
  );
}

/**
 * Categories that actually have businesses.
 *
 * `/directory/categories/active` rather than the full category list, so
 * the hub's filter chips can never offer a category that returns nothing
 * — an empty filter result reads as a broken page, not as an honest
 * "none here".
 */
export async function fetchActiveCategories(): Promise<ActiveCategory[]> {
  const page = await getJson<{ items: ActiveCategory[] }>(
    "/directory/categories/active?limit=50",
    DIRECTORY_REVALIDATE,
  );
  return page?.items ?? [];
}

/** Metres → "1.4 km", or null when the business has no usable location.
 * E1 returns UNLOCATABLE_M for those, and a "1000000 km" chip would be
 * worse than no chip. Imported from lib/home so the hub and the home row
 * cannot disagree about what "unlocatable" means. */
export function distanceLabel(distanceM: number): string | null {
  return distanceM < UNLOCATABLE_M
    ? `${(distanceM / 1000).toFixed(1)} km`
    : null;
}


/** A federated hit — a search result plus the vertical whose index produced
 * it. `sites` (on SearchHit) is which sites a business COVERS; `source_site`
 * is where the row came from. The hub needs the second to label a card and
 * send the visitor to the right domain. */
export interface FederatedHit extends SearchHit {
  source_site: string;
}

export interface FederatedPage {
  items: FederatedHit[];
  /** Sites that actually answered. A vertical whose index is empty or down
   * is absent rather than silently folded in, so the UI can be honest about
   * what it searched. */
  searched: string[];
}

/**
 * A-U4 W3 (D64) — cross-vertical search for the hub.
 *
 * agri.in is the family's hub, so a search here should be able to say "this
 * also exists on milk.in". Deliberately bounded and uncursored: see the
 * backend route's docstring — merging relevance across independent Meili
 * indexes into one resumable cursor is a different problem, and depth
 * belongs in each vertical's own search.
 *
 * Empty on any failure. A dead federation must cost the rail, never the
 * agri results the visitor actually came for.
 */
export async function searchFederated(options: {
  q: string;
  pincode?: string | undefined;
  limit?: number | undefined;
}): Promise<FederatedPage> {
  const params = new URLSearchParams({ q: options.q });
  if (options.pincode) params.set("pincode", options.pincode);
  params.set("limit", String(options.limit ?? 4));
  return (
    (await getJson<FederatedPage>(`/search/federated?${params}`, SEARCH_REVALIDATE)) ?? {
      items: [],
      searched: [],
    }
  );
}

/* ── A-U6 · the category landing (`/directory/[category]/[pincode]`) ────── */

/** A pincode's district never changes. A day is a short window for a fact
 * that is effectively permanent, and it keeps a flag flip visible same-day. */
const DISTRICT_REVALIDATE = 86_400;

/**
 * "641001" → "Coimbatore", for the category landing's title and crumb.
 *
 * There is no geo lookup endpoint. `GET /market/today/{pincode}` is the only
 * public read that resolves a pincode to its district, so that is what this
 * calls — deliberately taking one field off a larger payload rather than
 * inventing a district table the backend does not have.
 *
 * The route is gated by the `agri_today` flag and 404s while it is off, so
 * this returns null often enough that null must be a first-class answer: the
 * page falls back to "near 641001" rather than showing a district it cannot
 * prove.
 */
export async function fetchDistrict(pincode: string): Promise<string | null> {
  const body = await getJson<{ district?: string | null }>(
    `/market/today/${encodeURIComponent(pincode)}`,
    DISTRICT_REVALIDATE,
  );
  const district = body?.district;
  return typeof district === "string" && district.trim() ? district : null;
}

/** One row of `GET /catalog/businesses/{slug}/products` (public, approved-only). */
export interface CatalogProduct {
  id: string;
  name: string;
  slug: string;
  business_name: string | null;
  business_slug: string | null;
  price_display: string | null;
  specs: Record<string, unknown> | null;
  images: string[] | null;
}

/** A business's approved catalogue. Empty on any failure — a catalogue
 * service having a bad minute costs the strip, never the page. */
export async function fetchBusinessProducts(
  slug: string,
  limit = 6,
): Promise<CatalogProduct[]> {
  const page = await getJson<{ items: CatalogProduct[] }>(
    `/catalog/businesses/${encodeURIComponent(slug)}/products?limit=${limit}`,
    DIRECTORY_REVALIDATE,
  );
  return page?.items ?? [];
}

/**
 * The category landing's product strip.
 *
 * There is no "products in category X" read: `/catalog/verticals/{v}/products`
 * is keyed by VERTICAL, and a category ("dairy") is not a vertical ("milk") —
 * no mapping between them is exposed. Federated `/search?kind=product` is the
 * other candidate and is not usable either: its agri index has no filterable
 * attributes configured, so `kind` filtering 500s.
 *
 * So the strip is built from the businesses ALREADY on the page: their own
 * approved catalogues, one product each until the strip is full. That makes
 * the claim it renders exactly true — these are products from sellers serving
 * this pincode — instead of a category-wide claim nothing can substantiate.
 * One product per business, so a single large catalogue cannot own the strip
 * (the same rule the home's review strip follows).
 */
export async function fetchStripProducts(
  businesses: CoverageItem[],
  want = 4,
): Promise<CatalogProduct[]> {
  const sources = businesses.slice(0, want * 2);
  const lists = await Promise.all(
    sources.map((business) => fetchBusinessProducts(business.slug, 2)),
  );
  const strip: CatalogProduct[] = [];
  for (const [index, list] of lists.entries()) {
    const first = list[0];
    if (!first) continue;
    const source = sources[index];
    strip.push({
      ...first,
      business_name: first.business_name ?? source?.name ?? null,
      business_slug: first.business_slug ?? source?.slug ?? null,
    });
    if (strip.length === want) break;
  }
  return strip;
}
