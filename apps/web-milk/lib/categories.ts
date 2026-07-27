/** D27 dairy service categories — slugs mirror alembic 0026 exactly. */
export const DAIRY_CATEGORIES = [
  "veterinarian",
  "feed-supplier",
  "dairy-farm",
  "cooperative",
] as const;

export type DairyCategory = (typeof DAIRY_CATEGORIES)[number];

/** JSON message keys can't contain "-": slug → ui.dairyCategories key. */
export const CATEGORY_MESSAGE_KEY: Record<DairyCategory, string> = {
  veterinarian: "veterinarian",
  "feed-supplier": "feedSupplier",
  "dairy-farm": "dairyFarm",
  cooperative: "cooperative",
};

export function isDairyCategory(value: string): value is DairyCategory {
  return (DAIRY_CATEGORIES as readonly string[]).includes(value);
}
