import { TypeFilterRow } from "@agri/ui";
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
 * read (D23) — the home has no filter state of its own to diverge from it.
 */
export async function MilkTypeChips({
  filters,
  milkTypes,
  base,
}: {
  filters: string[];
  milkTypes: ProductCategory[];
  base: string;
}) {
  if (filters.length <= 1) return null;
  const t = await getTranslations("ui.home.types");
  const labels = new Map(milkTypes.map((m) => [m.value, m.label]));
  return (
    <div className="mt-3">
      <TypeFilterRow label={t("title")}>
        {filters.map((key) => {
          const label = key === "all" ? t("all") : (labels.get(key) ?? milkTypeMeta(key).en);
          return (
            <Link
              key={key}
              href={key === "all" ? base : `${base}?type=${encodeURIComponent(key)}`}
              className="flex min-w-[86px] shrink-0 flex-col items-center gap-[3px] rounded-card border-2 border-cream-line bg-card px-3.5 py-2.5 text-center text-ink no-underline"
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
