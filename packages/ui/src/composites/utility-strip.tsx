import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * Utility strip (U1 §1): the thin brand-deep bar that sits ABOVE the main
 * header — tagline · spacer · secondary links · hotline chip.
 *
 * Deliberately static server-rendered markup with no client island. The
 * header's right cluster already hydrates three islands (auth, coins, bell)
 * and `site-footer.tsx` records that a fourth item there moved CLS from
 * 0.098 to 0.136 as they populated. This strip carries the links that used
 * to crowd that row, and it cannot shift because nothing in it hydrates.
 */
export function UtilityStrip({
  tagline,
  links,
  hotline,
  className,
}: {
  tagline: ReactNode;
  /** Secondary links — `UtilityLink` children. Hidden below 768px. */
  links?: ReactNode;
  /** Hotline chip. Omit (or pass a falsy value) and the chip is not rendered
   * at all — the strip itself still renders, per §1's "render slot even if
   * value empty → hide chip". */
  hotline?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("bg-brand-deep text-[12px] text-brand-soft-2", className)} data-testid="utility-strip">
      <div className="mx-auto flex max-w-[1140px] items-center gap-4 px-4 py-1.5">
        <span>{tagline}</span>
        <span className="flex-1" />
        {links}
        {hotline ? (
          <span className="whitespace-nowrap rounded-[5px] bg-accent px-2.5 py-[3px] font-medium text-accent-ink">
            {hotline}
          </span>
        ) : null}
      </div>
    </div>
  );
}

/**
 * A secondary link in the utility strip. `max-md:hidden` is the reference's
 * `@media(max-width:767px){.util .link{display:none}}` — on a phone the strip
 * keeps only the tagline and the hotline chip.
 *
 * `.tap-target` expands the hit area to the 44px floor (design-system.md
 * §1.5) WITHOUT growing the rendered 12px row — the reference strip is 26px
 * tall and a real 44px box would double the height of the bar.
 */
export function UtilityLink({
  href,
  children,
  className,
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <a
      href={href}
      className={cn("tap-target whitespace-nowrap no-underline max-md:hidden", className)}
    >
      {children}
    </a>
  );
}
