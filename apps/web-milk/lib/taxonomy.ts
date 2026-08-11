const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * The dairy product taxonomy (M1). The VALUE SET, its labels and its icon
 * keys all come from the D17 milk spec-schema — `GET
 * /catalog/verticals/milk/schema`. Nothing here enumerates categories:
 * adding one to the schema must light it up everywhere with no code change
 * (NON-NEGOTIABLE 1).
 */
export interface ProductCategory {
  value: string;
  label: string;
  vern: string;
  icon: string;
}

/**
 * icon KEY → glyph. Presentation only, and deliberately not exhaustive:
 * an unknown key falls back to 🥛, so a brand-new schema value renders with
 * its correct label immediately and only its glyph is a follow-up.
 *
 * Every glyph is Unicode ≤ 13.0 on purpose — rural Android devices ship
 * older emoji fonts and a newer codepoint renders as tofu (▯).
 */
const CATEGORY_ICONS: Record<string, string> = {
  milk: "🥛",
  ghee: "🍯",
  paneer: "🧀",
  "milk-powder": "🥄",
  yogurt: "🍶",
  lassi: "🧋",
  curd: "🍚",
  buttermilk: "🥤",
  cheese: "🫕",
  butter: "🧈",
  cream: "🍦",
  khoa: "🍥",
  "flavoured-milk": "🍫",
};

const FALLBACK_ICON = "🥛";

export function categoryIcon(key: string): string {
  return CATEGORY_ICONS[key] ?? FALLBACK_ICON;
}

interface SchemaOptionMeta {
  label?: Record<string, string>;
  icon?: string;
}

/** The vernacular second line: Tamil for en/ta readers, Hindi for hi. */
function vernacularFor(label: Record<string, string>, locale: string, primary: string): string {
  const vern = locale === "hi" ? label.hi : label.ta;
  return vern && vern !== primary ? vern : "";
}

export function categoriesFromSchema(
  payload: unknown,
  locale: string,
  fieldKey = "category",
): ProductCategory[] {
  const fields = (payload as { fields?: unknown } | null)?.fields;
  if (!Array.isArray(fields)) return [];
  const field = fields.find(
    (f) => (f as { key?: string })?.key === fieldKey,
  ) as { options?: unknown; option_meta?: Record<string, SchemaOptionMeta> } | undefined;
  if (!field || !Array.isArray(field.options)) return [];
  const meta = field.option_meta ?? {};
  return field.options
    .filter((value): value is string => typeof value === "string")
    .map((value) => {
      const label = meta[value]?.label ?? {};
      const primary = label[locale] ?? label.en ?? value;
      return {
        value,
        label: primary,
        vern: vernacularFor(label, locale, primary),
        icon: categoryIcon(meta[value]?.icon ?? value),
      };
    });
}

/**
 * Server-side public read — direct to the backend, NOT the BFF proxy, with
 * ISR caching. Returns [] on any failure so a build with no backend still
 * succeeds and self-heals at the next revalidate (same contract as
 * `fetchCoveredPincodes` in lib/milk.ts, which sitemap generation relies on).
 */
export async function fetchProductCategories(locale: string): Promise<ProductCategory[]> {
  return (await fetchSchemaOptions(locale, "category")) ?? [];
}

/**
 * The `milk_type` value set (cow / buffalo / a2 / toned / organic / mixed),
 * read from the SAME D17 schema and the SAME `option_meta` labels as the
 * categories. This is what makes the §5c type chips localise: at `/ta` the
 * primary label is the Tamil one, so nothing English survives.
 *
 * `MILK_TYPE_META` in `lib/milk.ts` is presentation-only fallback (icons and
 * a vernacular line for legacy callers) — it must never be the label source.
 */
export async function fetchMilkTypes(locale: string): Promise<ProductCategory[]> {
  return (await fetchSchemaOptions(locale, "milk_type")) ?? [];
}

async function fetchSchemaOptions(
  locale: string,
  fieldKey: string,
): Promise<ProductCategory[] | null> {
  try {
    const res = await fetch(`${API}/catalog/verticals/milk/schema`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    return categoriesFromSchema(await res.json(), locale, fieldKey);
  } catch {
    return null;
  }
}
