const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * Business-category taxonomy (U1b) — the data-driven replacement for the
 * D27 hardcoded slug list. `GET /directory/categories/active` returns the
 * categories that at least one ACTIVE business is assigned to, with that
 * count; every consumer surface (results chips, home service tiles, /c
 * landing pages, brand-page chips, footer) renders exactly this set, so
 * adding a category row + one active business lights them all up with zero
 * frontend change.
 */
export interface BusinessCategory {
  slug: string;
  /** Locale-keyed display name straight from the directory row. */
  name: Record<string, string>;
  sort_order: number;
  business_count: number;
}

/** Walks the cursor-paginated feed. Bounded: the taxonomy is tens of rows,
 * and 5 pages of 100 is far more than a browse surface should ever list. */
export async function fetchBusinessCategories(): Promise<BusinessCategory[]> {
  const out: BusinessCategory[] = [];
  let cursor: string | null = null;
  try {
    for (let page = 0; page < 5; page++) {
      const qs: string = cursor
        ? `?cursor=${encodeURIComponent(cursor)}&limit=100`
        : "?limit=100";
      const res = await fetch(`${API}/directory/categories/active${qs}`, {
        next: { revalidate: 3600 },
      });
      if (!res.ok) return out;
      const body = (await res.json()) as {
        items: BusinessCategory[];
        next_cursor: string | null;
      };
      out.push(...body.items);
      if (!body.next_cursor) break;
      cursor = body.next_cursor;
    }
  } catch {
    // Backend unreachable (CI builds run with no backend) — degrade to an
    // empty taxonomy; the surfaces collapse rather than crash.
  }
  return out.sort((a, b) => a.sort_order - b.sort_order);
}

/** The row's own localized name, falling back en → slug. Category names are
 * directory data (like business names), so an untranslated row legitimately
 * shows its en value rather than faking a translation. Accepts any
 * category-shaped row (the taxonomy read and the brand page's assigned
 * `CategoryOut`s share slug + name). */
export function categoryLabel(
  category: { slug: string; name: Record<string, string> },
  locale: string,
): string {
  return category.name[locale] ?? category.name.en ?? category.slug;
}

/**
 * Copy-enrichment map for the /c landing descriptions: slugs that shipped
 * with hand-written ui.dairyCategories.* message copy. PRESENTATION ONLY —
 * the taxonomy never consults this; an unknown slug simply falls back to the
 * generic localized description, exactly like the icon map falls back to 🥛.
 */
export const CATEGORY_MESSAGE_KEY: Record<string, string> = {
  veterinarian: "veterinarian",
  "feed-supplier": "feedSupplier",
  "dairy-farm": "dairyFarm",
  cooperative: "cooperative",
};

/** Presentation-only icon map, same contract as the product-category icons:
 * unknown slugs get the neutral glyph. */
export const CATEGORY_ICONS: Record<string, string> = {
  veterinarian: "🐄",
  "feed-supplier": "🌾",
  "dairy-farm": "🏭",
  cooperative: "🤝",
  dairy: "🥛",
  shop: "🏪",
};

export function categoryIcon(slug: string): string {
  return CATEGORY_ICONS[slug] ?? "🥛";
}
