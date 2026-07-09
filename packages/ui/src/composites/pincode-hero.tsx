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
  className,
}: {
  title: ReactNode;
  subtitle: ReactNode;
  /** PincodeInput + GpsPill. */
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("px-4 pb-[22px] pt-[26px] text-center text-white", className)}>
      <h1 className="mb-1 font-display text-[clamp(22px,4.5vw,32px)] font-extrabold">{title}</h1>
      <p className="mb-4 text-sm opacity-90">{subtitle}</p>
      {children}
    </div>
  );
}
