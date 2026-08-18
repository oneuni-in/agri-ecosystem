import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * Header stack: gradient header → topbar (logo+tagline · pills · coins ·
 * avatar) → searchband (or PincodeHero as children).
 */
export function HeaderStack({
  logo,
  tagline,
  location,
  right,
  children,
  flat = false,
  nowrap = false,
  className,
}: {
  logo: ReactNode;
  tagline: ReactNode;
  /** LocationPill slot, next to the logo. */
  location?: ReactNode;
  /** Right cluster: LangSwitcher · CoinsPill · Avatar. */
  right?: ReactNode;
  /** Searchband content (SearchBar) or a PincodeHero. */
  children?: ReactNode;
  /** Flat brand fill instead of the gradient (U1 §2 `.hdr{background:var(--mk)}`),
   * for headers that sit under a utility strip and above a separate hero. */
  flat?: boolean;
  /** Single non-wrapping row (U1 §2). The default wrapping row is kept for
   * agri.in, whose header carries a full SearchBand. */
  nowrap?: boolean;
  className?: string;
}) {
  return (
    <header className={cn(flat ? "bg-brand" : "bg-header-gradient", className)}>
      <div
        className={cn(
          "mx-auto flex max-w-[1140px] items-center gap-3 px-4 pb-1 pt-3 text-white",
          nowrap ? "flex-nowrap max-md:gap-2" : "flex-wrap",
        )}
      >
        {/* Brand lockup. Two stacked lines with their OWN line-heights — the
            previous `-mt-[3px]` + `leading-tight` pulled the tagline into the
            logo's box, and because the tagline carries Tamil/Devanagari
            (பால் · दूध), whose ascenders and descenders exceed the Latin
            em-box, the two lines visibly collided in EN/TA (U1 §2, "fixes the
            EN/TA overlap defect"). 1.35 on the tagline is the same headroom
            `.vern` reserves for mother-tongue text. */}
        {/* Clip the TAGLINE, never the wordmark. Both lines below are
            `whitespace-nowrap` on purpose (see their comments), and nowrap
            text does not shrink — so without a clip this column spilled past
            its box at 360px and drew underneath the location pill. Adding
            `min-w-0` clipped the spill but took ".in" off the brand with it,
            which is a worse defect than the one being fixed. No `min-w-0`
            means the column still floors at the wordmark's width; the
            `truncate` on the tagline absorbs the rest. */}
        <div className={cn("flex flex-col", nowrap && "shrink-0 sm:min-w-0 sm:shrink sm:overflow-hidden")}>
          <span className="whitespace-nowrap font-display text-[22px] font-extrabold leading-[1.1] tracking-[-0.02em]">
            {logo}
          </span>
          {/* `--brand-soft`, not `opacity-85` and not `--brand-soft-2`.
              Opacity blending is what `.vern` already bans (it silently eats
              contrast ratios). --brand-soft-2 is the reference's choice here,
              but measured on the flat --brand fill it is 3.94:1 — under the
              4.5:1 AA floor for 11px text (axe `color-contrast`). It stays
              the right token one step darker, on --brand-deep, which is where
              the utility strip uses it (7.0:1). --brand-soft is 7.4:1 here. */}
          {/* Hidden below `sm`, truncated above it. This line carries Tamil
              and Devanagari, so letting it wrap turns a 56px bar into a 100px
              one on a 360px phone — but keeping it nowrap at that width made
              it spill under the location pill, and squeezing it instead cost
              the pill its pincode. It is the only decorative element in the
              row: the wordmark identifies the site and the pill says which
              place the page is showing, so on a phone the tagline is what
              yields. It returns in full from 640px up. */}
          <small className="truncate font-body text-[11px] max-sm:hidden font-semibold leading-[1.35] tracking-normal text-brand-soft">
            {tagline}
          </small>
        </div>
        {location}
        <div className={cn("ml-auto flex items-center gap-2", nowrap && "shrink-0")}>{right}</div>
      </div>
      {children}
    </header>
  );
}

/** Searchband slot inside the header stack (`.searchband`). */
export function SearchBand({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto max-w-[1140px] px-4 pb-4 pt-1.5", className)}>{children}</div>;
}
