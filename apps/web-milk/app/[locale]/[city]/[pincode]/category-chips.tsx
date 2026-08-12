import { cn } from "@agri/ui";
import { getLocale, getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { categoryLabel, fetchBusinessCategories } from "@/lib/categories";

/**
 * Category chip row (D27 Task 13, rebound in U1b) — the chip SET comes from
 * the public taxonomy read (`fetchBusinessCategories`, categories with ≥1
 * active business), never a list in code; labels are the directory rows' own
 * localized names. Reuses the type-filter chip classes so the two chip rows
 * read as one system. Plain navigation `Link`s to `?category=` —
 * server-rendered, back-button-safe, zero JS for the happy path.
 */
export async function CategoryChips({
  base,
  active,
}: {
  base: string; // canonical page path, e.g. /coimbatore/641001 (D28)
  active: string | null;
}) {
  const [t, locale, categories] = await Promise.all([
    getTranslations("ui"),
    getLocale(),
    fetchBusinessCategories(),
  ]);
  if (categories.length === 0 && active === null) return null; // taxonomy dark — collapse
  const chipClass = (on: boolean) =>
    cn(
      // min-h-[44px]: single-line chips measured 40px tall, under the 44px
      // minimum tap target (design-system.md §1.5). The type-filter chips clear
      // it only because their icon adds a second line (D29).
      "flex min-h-[44px] min-w-[86px] shrink-0 flex-col items-center justify-center gap-[3px] rounded-card border-2 border-cream-line bg-card px-3.5 py-2.5 text-center text-ink no-underline",
      on && "border-brand bg-brand-soft",
    );

  return (
    <div
      role="group"
      aria-label={t("categoryBrowse.rowLabel")}
      className="flex gap-[9px] overflow-x-auto pb-1"
      data-testid="category-chip-row"
    >
      <Link
        href={base}
        aria-current={active === null ? "true" : undefined}
        className={chipClass(active === null)}
        data-testid="category-chip-all"
      >
        <b className="text-xs">{t("categoryBrowse.allMilk")}</b>
      </Link>
      {categories.map((category) => {
        const on = category.slug === active;
        return (
          <Link
            key={category.slug}
            href={`${base}?category=${category.slug}`}
            aria-current={on ? "true" : undefined}
            className={chipClass(on)}
            data-testid={`category-chip-${category.slug}`}
          >
            <b className="text-xs">{categoryLabel(category, locale)}</b>
          </Link>
        );
      })}
    </div>
  );
}
