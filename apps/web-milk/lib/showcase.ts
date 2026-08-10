import { categoriesFromSchema } from "./taxonomy";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export interface ShowcaseProduct {
  id: string;
  name: string;
  slug: string;
  businessName: string;
  businessSlug: string;
  priceDisplay: string | null;
  categoryLabel: string | null;
  image: string | null;
}

interface WireProduct {
  id: string;
  name: string;
  slug: string;
  business_name: string;
  business_slug: string;
  price_display: string | null;
  specs: Record<string, unknown> | null;
  images: string[] | null;
}

/**
 * §7's ONE accessor: `get_showcase_products(vertical, limit)`.
 *
 * Reads approved, active rows through the EXISTING public catalog endpoint
 * (`GET /catalog/verticals/{vertical}/products`) — the same engine the
 * category pages use — so the showcase can never drift from the real catalog.
 * No new table and no new API surface: U1 allows seed/config entries only,
 * and the rows here are the ordinary seeded product rows with media attached
 * by `scripts/seed_sample_media.py`.
 *
 * `vertical` is a parameter because this section is explicitly cross-vertical:
 * when TheOrganic's catalog goes live it becomes `get_showcase_products
 * ("organic", …)` with no change to the component that renders it.
 */
export async function getShowcaseProducts(
  vertical: string,
  limit: number,
  locale: string,
): Promise<ShowcaseProduct[]> {
  const [wire, schema] = await Promise.all([
    fetchJson<{ items: WireProduct[] }>(
      `/catalog/verticals/${encodeURIComponent(vertical)}/products?limit=${limit}`,
    ),
    fetchJson<unknown>(`/catalog/verticals/${encodeURIComponent(vertical)}/schema`),
  ]);
  if (!wire) return [];
  // Localised category labels come from the schema's option_meta, the same
  // source the category bar and type chips read.
  const labels = new Map(
    (schema ? categoriesFromSchema(schema, locale) : []).map((c) => [c.value, c.label]),
  );
  return wire.items.map((item) => {
    const category = typeof item.specs?.category === "string" ? item.specs.category : null;
    return {
      id: item.id,
      name: item.name,
      slug: item.slug,
      businessName: item.business_name,
      businessSlug: item.business_slug,
      priceDisplay: item.price_display,
      categoryLabel: category ? (labels.get(category) ?? category) : null,
      image: item.images?.[0] ?? null,
    };
  });
}

async function fetchJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
