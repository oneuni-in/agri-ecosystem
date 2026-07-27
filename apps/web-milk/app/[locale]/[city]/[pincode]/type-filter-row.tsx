import { cn } from "@agri/ui";

import { Link } from "@/i18n/navigation";
import { milkTypeMeta } from "@/lib/milk";

/**
 * `.tf` type filter row (design-system.md §2/§74): horizontally scrollable
 * 86px-min chips, icon + English + mother tongue (UX law 1); active = brand
 * border + brand-soft bg. The filter SET is schema-driven — it comes
 * straight from the backend `filters` array (`["all", ...milk_type
 * options]`, Task 5/8), never hardcoded here; only icon/vernacular are
 * presentational, via `milkTypeMeta`.
 *
 * Plain `<Link href="?type=...">`s, no client fetch — the pincode page
 * (Task 10) reads `?type=` server-side, so results, filters, and URL stay
 * shareable/back-button-safe with zero JS required for the happy path.
 */
export function TypeFilterRow({
  base,
  filters,
  active,
}: {
  base: string; // canonical page path, e.g. /coimbatore/641001 (D28)
  filters: string[];
  active: string;
}) {
  return (
    <div
      role="group"
      aria-label="Milk type"
      className="flex gap-[9px] overflow-x-auto pb-1"
      data-testid="type-filter-row"
    >
      {filters.map((key) => {
        const meta = milkTypeMeta(key);
        const on = key === active;
        const href = key === "all" ? base : `${base}?type=${key}`;
        return (
          <Link
            key={key}
            href={href}
            aria-current={on ? "true" : undefined}
            className={cn(
              "flex min-w-[86px] shrink-0 flex-col items-center gap-[3px] rounded-card border-2 border-line bg-card px-3.5 py-2.5 text-center text-ink no-underline",
              on && "border-brand bg-brand-soft",
            )}
          >
            <span aria-hidden="true" className="text-[26px] leading-none">
              {meta.icon}
            </span>
            <b className="text-xs">
              {meta.en}
              {meta.vern ? <span className="vern">{meta.vern}</span> : null}
            </b>
          </Link>
        );
      })}
    </div>
  );
}
