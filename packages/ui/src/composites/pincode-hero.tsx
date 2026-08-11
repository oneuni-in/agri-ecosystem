import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * Milk.in swaps the searchband for this pincode hero (`.pin-hero`):
 * centered h1 clamp 22–32px, sub-line, pinbox, GPS pill.
 */
export function PincodeHero({
  title,
  subtitle,
  children,
  banded = false,
  className,
}: {
  title: ReactNode;
  subtitle: ReactNode;
  /** PincodeInput + GpsPill. */
  children: ReactNode;
  /** U1 §4: render as a self-contained rounded search band inside the page
   * gutter (`.search-band`) instead of a full-bleed hero on a page-wide
   * gradient. The un-banded form stays the default for existing callers. */
  banded?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "px-4 pb-[22px] pt-[26px] text-center text-white",
        banded && "rounded-card bg-header-gradient",
        className,
      )}
    >
      <h1 className="mb-1 font-display text-[clamp(22px,4.5vw,32px)] font-extrabold">{title}</h1>
      {/* A token, not opacity: the sub-line is 14px on the brand fill and
          opacity-90 puts it under the AA floor (same rule as `.vern`). */}
      <p className={cn("mb-4 text-sm", banded ? "text-brand-soft" : "opacity-90")}>{subtitle}</p>
      {children}
    </div>
  );
}
