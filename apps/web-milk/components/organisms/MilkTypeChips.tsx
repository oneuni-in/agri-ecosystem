import { cn, TypeFilterRow } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { milkTypeMeta } from "@/lib/milk";
import type { ProductCategory } from "@/lib/taxonomy";

/**
 * §5c — milk-type filter chips.
 *
 * The chip SET comes from the backend's schema-driven `filters` array
 * (`["all", ...milk_type options]`) exactly as D23's existing chip row does —
 * this is a restyle of that logic, not a rebuild. LABELS come from the D17
 * `option_meta`, so the row is fully localised; `milkTypeMeta` supplies the
 * icon only, with a graceful fallback for a schema value it has never seen.
 *
 * Chips link to the pincode results page, which is where `?type=` is actually
 * read (D23). On that page itself the SAME component renders the row with
 * `active` set, so the home and the results surface share one chip binding.
 */
export async function MilkTypeChips({
  filters,
  milkTypes,
  base,
  active,
  testId,
}: {
  filters: string[];
  milkTypes: ProductCategory[];
  base: string;
  /** The `?type=` value currently applied (results page); the active chip
   * gets `aria-current` + the brand border. Omitted on the home. */
  active?: string;
  /** Override for surfaces whose e2e contract names the row (the results
   * page's `type-filter-row`). */
  testId?: string;
}) {
  if (filters.length <= 1) return null;
  const t = await getTranslations("ui.home.types");
  const labels = new Map(milkTypes.map((m) => [m.value, m.label]));
  return (
    <div className="mt-3">
      <TypeFilterRow label={t("title")} {...(testId ? { "data-testid": testId } : {})}>
        {filters.map((key) => {
          const label = key === "all" ? t("all") : (labels.get(key) ?? milkTypeMeta(key).en);
          const on = active !== undefined && key === active;
          return (
            <Link
              key={key}
              href={key === "all" ? base : `${base}?type=${encodeURIComponent(key)}`}
              aria-current={on ? "true" : undefined}
              className={cn(
                "flex min-w-[86px] shrink-0 flex-col items-center gap-[3px] rounded-card border-2 border-cream-line bg-card px-3.5 py-2.5 text-center text-ink no-underline",
                on && "border-brand bg-brand-soft",
              )}
              data-testid={`home-type-${key}`}
            >
              <span aria-hidden="true" className="text-[26px] leading-none">
                {milkTypeMeta(key).icon}
              </span>
              <b className="text-xs font-semibold">{label}</b>
            </Link>
          );
        })}
      </TypeFilterRow>
    </div>
  );
}
