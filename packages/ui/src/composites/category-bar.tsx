import type { ReactNode } from "react";

import { cn } from "../lib/cn";

import { CategoryBarFilters } from "./category-bar-filters";

/**
 * Category bar (U1 §5): the white text-nav bar under the search band.
 *
 * The overflow rule is a NON-NEGOTIABLE (U1 NN5 — "never wraps at any
 * viewport 320–1920px"), so it is encoded here rather than left to callers:
 *   · `flex-nowrap` + `whitespace-nowrap` on the scroller
 *   · `flex-none` on every child (a shrinking child is how a nowrap row
 *     still ends up looking wrapped/clipped)
 *   · horizontal scroll with the scrollbar hidden on both engines
 *   · an edge fade via `mask-image`, which is alpha-only — it needs no
 *     colour, so it survives the no-raw-hex rule and works over any surface
 *
 * The border and background sit on the OUTER element and the mask on the
 * INNER scroller, so the fade never eats the bar's own hairline border.
 */
export function CategoryBar({
  label,
  children,
  filters,
  className,
}: {
  /** Accessible name for the nav landmark. */
  label: string;
  /** `CategoryBarLink` children. */
  children: ReactNode;
  /** Attribute filters. Pinned right and desktop-only — the bar applies that
   * treatment itself, so callers pass plain links. */
  filters?: ReactNode;
  className?: string;
}) {
  return (
    <nav
      aria-label={label}
      data-testid="category-bar"
      className={cn(
        "flex items-center rounded-btn border border-cream-line bg-card px-4 py-2.5",
        className,
      )}
    >
      <div className="flex min-w-0 flex-1 flex-nowrap items-center gap-[22px] overflow-x-auto whitespace-nowrap [-webkit-overflow-scrolling:touch] [mask-image:linear-gradient(to_right,transparent_0,black_18px,black_calc(100%-18px),transparent_100%)] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden [&>*]:flex-none">
        {children}
      </div>
      {/* Outside the scroller on purpose: the reference pins these to the
          right edge of the bar, and a category list long enough to scroll
          (13 schema values today) would otherwise push them out of sight the
          moment the row overflows. */}
      {filters ? <CategoryBarFilters>{filters}</CategoryBarFilters> : null}
    </nav>
  );
}

/**
 * One entry in the bar. `active` draws the reference's 2px brand underline
 * without adding height (negative margin cancels the extra padding, so the
 * bar's row height is identical active or not — no CLS as the active item
 * moves between pages). `more` is the trailing "All N ›" link.
 */
export function CategoryBarLink({
  href,
  active = false,
  more = false,
  children,
  className,
}: {
  href: string;
  active?: boolean;
  more?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <a
      href={href}
      {...(active ? { "aria-current": "page" as const } : {})}
      className={cn(
        "tap-target text-[13px] no-underline",
        active
          ? "-mb-1.5 border-b-2 border-brand pb-1.5 font-medium text-brand-deep"
          : more
            ? "text-brand"
            : "text-ink",
        className,
      )}
    >
      {children}
    </a>
  );
}

