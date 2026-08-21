/**
 * A-U6 W2 — the catalog read layer for `/products/[slug]`.
 *
 * `GET /catalog/products/{slug}` returns the product AND the spec schema it
 * was validated against, which is the whole point of the A2 reference's
 * claim that the spec table is "rendered from admin spec-schema — no
 * hardcoded fields". Nothing in this file knows what a tractor or a litre of
 * milk is: field order, labels and enum wording all come off the wire, so a
 * new vertical gets a correct spec table without a line changing here.
 *
 * Products pin `schema_version` at create and reads never re-validate (D17),
 * so an old product keeps rendering after the schema moves on — the fields
 * returned alongside it are the ones it was pinned to.
 *
 * Same failure contract as lib/directory: server-side, public-read, failure
 * collapses to null. A dead catalog costs the page a 404, never a 500.
 */

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** A product changes when its seller edits it — five minutes, like coverage. */
const CATALOG_REVALIDATE = 300;

export interface CatalogProduct {
  id: string;
  business_id: string;
  business_name: string | null;
  business_slug: string | null;
  vertical_slug: string;
  schema_version: number;
  name: string;
  slug: string;
  specs: Record<string, unknown> | null;
  price_display: string | null;
  status: string;
  images: string[] | null;
  created_at: string | null;
}

/** One field definition from the pinned spec schema. */
export interface SpecField {
  key: string;
  type: "string" | "number" | "boolean" | "enum";
  label: Record<string, string>;
  /** Section heading, e.g. "basics" / "nutrition". Absent = ungrouped. */
  group?: string | null;
  /** Rendered after a number, e.g. "%". */
  unit?: string | null;
  options?: string[] | null;
  /** Per-option display wording. Not every enum has it (D17 M1 option_meta),
   * so a missing entry falls back to the raw option value. */
  option_meta?: Record<string, { icon?: string; label?: Record<string, string> }> | null;
}

export interface ProductDetail {
  product: CatalogProduct;
  schema_fields: SpecField[];
}

export async function fetchProduct(slug: string): Promise<ProductDetail | null> {
  try {
    const res = await fetch(`${API}/catalog/products/${encodeURIComponent(slug)}`, {
      next: { revalidate: CATALOG_REVALIDATE },
    });
    if (!res.ok) return null;
    const body = (await res.json()) as ProductDetail;
    if (!body?.product?.slug) return null;
    return { product: body.product, schema_fields: body.schema_fields ?? [] };
  } catch {
    return null;
  }
}

/** Pick a translated string, falling back to English then the first value. */
export function pickLabel(
  locale: string,
  label: Record<string, string> | undefined | null,
): string | null {
  if (!label) return null;
  return label[locale] ?? label["en"] ?? Object.values(label)[0] ?? null;
}

export interface SpecRow {
  key: string;
  group: string | null;
  label: string;
  value: string;
}

/**
 * The spec table's rows, in SCHEMA order — not object order.
 *
 * A field the product has no value for is omitted rather than rendered
 * blank: the schema describes what a vertical CAN say, and a product is not
 * obliged to say all of it. A spec the schema does not define is omitted
 * too — the schema is the contract for what this table means, and a stray
 * key from an older pin would render without a label or a type.
 */
export function specRows(
  specs: Record<string, unknown> | null,
  fields: SpecField[],
  locale: string,
): SpecRow[] {
  if (!specs) return [];
  const rows: SpecRow[] = [];
  for (const field of fields) {
    const raw = specs[field.key];
    if (raw === null || raw === undefined || raw === "") continue;

    let value: string;
    if (field.type === "boolean") {
      value = raw ? "Yes" : "No";
    } else if (field.type === "enum") {
      const meta = field.option_meta?.[String(raw)];
      value = pickLabel(locale, meta?.label) ?? String(raw);
    } else if (field.type === "number") {
      value = field.unit ? `${raw} ${field.unit}` : String(raw);
    } else {
      value = String(raw);
    }

    rows.push({
      key: field.key,
      group: field.group ?? null,
      label: pickLabel(locale, field.label) ?? field.key,
      value,
    });
  }
  return rows;
}

/** Rows grouped for the table's section headings, groups in first-seen
 * (schema) order, ungrouped rows last under no heading. */
export function groupSpecRows(rows: SpecRow[]): { group: string | null; rows: SpecRow[] }[] {
  const order: (string | null)[] = [];
  const byGroup = new Map<string | null, SpecRow[]>();
  for (const row of rows) {
    if (!byGroup.has(row.group)) {
      byGroup.set(row.group, []);
      order.push(row.group);
    }
    byGroup.get(row.group)?.push(row);
  }
  order.sort((a, b) => (a === null ? 1 : 0) - (b === null ? 1 : 0));
  return order.map((group) => ({ group, rows: byGroup.get(group) ?? [] }));
}

export interface RatingSummary {
  rating_avg: number | string | null;
  rating_count: number;
}

export interface ReviewItem {
  id: string;
  rating: number;
  body: string | null;
  created_at: string | null;
}

/**
 * Approved reviews for a PRODUCT. `review_target_type` has included
 * "product" since D18, so this is the same engine the business profile
 * reads, pointed at a different target — not a second review system.
 *
 * Read straight from the backend server-side, NOT through `/api/reviews`:
 * that proxy is auth-required by design and would 401 for a guest.
 */
export async function fetchProductReviews(
  productId: string,
): Promise<{ summary: RatingSummary; items: ReviewItem[] }> {
  const qs = `target_type=product&target_id=${encodeURIComponent(productId)}`;
  const empty = { summary: { rating_avg: null, rating_count: 0 }, items: [] };
  try {
    const [summaryRes, listRes] = await Promise.all([
      fetch(`${API}/reviews/summary?${qs}`, { next: { revalidate: CATALOG_REVALIDATE } }),
      fetch(`${API}/reviews?${qs}&limit=6`, { next: { revalidate: CATALOG_REVALIDATE } }),
    ]);
    return {
      summary: summaryRes.ok ? ((await summaryRes.json()) as RatingSummary) : empty.summary,
      items: listRes.ok ? (((await listRes.json()) as { items: ReviewItem[] }).items ?? []) : [],
    };
  } catch {
    return empty;
  }
}

export interface SellerBranch {
  id: string;
  address: string;
  state: string;
  district: string;
  pincode: string;
}

export interface SellerDetail {
  business: {
    id: string;
    name: string;
    slug: string;
    type: string;
    verification_status: string;
  };
  branches: SellerBranch[];
  categories: { slug: string; name: Record<string, string> }[];
}

/**
 * The business selling this product, for the "Sold by" card.
 *
 * Fetched for the BRANCH ID, so the seller card can run the same D18 reveal
 * the category cards run. As everywhere else, this payload carries no phone
 * number — only the reveal endpoint does.
 */
export async function fetchSeller(slug: string): Promise<SellerDetail | null> {
  try {
    const res = await fetch(`${API}/directory/businesses/${encodeURIComponent(slug)}`, {
      next: { revalidate: CATALOG_REVALIDATE },
    });
    if (!res.ok) return null;
    return (await res.json()) as SellerDetail;
  } catch {
    return null;
  }
}
