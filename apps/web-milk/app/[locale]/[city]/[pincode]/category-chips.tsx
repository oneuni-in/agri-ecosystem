import { cn } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { CATEGORY_MESSAGE_KEY, DAIRY_CATEGORIES, type DairyCategory } from "@/lib/categories";

/**
 * Category chip row (D27 Task 13) — reuses `TypeFilterRow`'s exact chip
 * classes (design-system.md §2/§74 `.tf`, ≥44px tap targets via
 * `px-3.5 py-2.5`) so the two chip rows read as one system. Rendered under
 * `TypeFilterRow` on the milk view (`active={null}`) and at the top of the
 * category view (`active={category}`), so the four dairy categories + "all
 * milk" stay one tap away from every covered pincode page. Plain navigation
 * `Link`s to `?category=` — server-rendered, back-button-safe, zero JS for
 * the happy path, same precedent as `TypeFilterRow`.
 */
export async function CategoryChips({
  base,
  active,
}: {
  base: string; // canonical page path, e.g. /coimbatore/641001 (D28)
  active: DairyCategory | null;
}) {
  const t = await getTranslations("ui");
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
      {DAIRY_CATEGORIES.map((slug) => {
        const on = slug === active;
        return (
          <Link
            key={slug}
            href={`${base}?category=${slug}`}
            aria-current={on ? "true" : undefined}
            className={chipClass(on)}
            data-testid={`category-chip-${slug}`}
          >
            <b className="text-xs">{t(`dairyCategories.${CATEGORY_MESSAGE_KEY[slug]}.name`)}</b>
          </Link>
        );
      })}
    </div>
  );
}
