import type { ReactNode } from "react";

import { cn } from "../lib/cn";
import { tintClass, type Tint } from "../components/category-tile";

/** Product grid (`.prodgrid`): auto-fill minmax(160px,1fr). */
export function ProductGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(160px,1fr))]", className)}>
      {children}
    </div>
  );
}

/**
 * Organic product card (`.pc2`): 110px tinted image area → cert badge →
 * 13.5px/800 title → brand·rating line → full-width brand "Where to buy 📍".
 */
export function ProductCard({
  image,
  tint,
  cert,
  title,
  brandLine,
  cta,
  className,
}: {
  /** Emoji/product visual for the 110px image area. */
  image: ReactNode;
  tint: Tint;
  /** Cert badge slot (Badge variant="cert"). */
  cert: ReactNode;
  title: ReactNode;
  /** `Kovai Naturals · ★ 4.8` line. */
  brandLine: ReactNode;
  cta: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col overflow-hidden rounded-card border border-line bg-card", className)}>
      <div
        aria-hidden="true"
        className={cn("flex h-[110px] items-center justify-center text-[44px] leading-none", tintClass[tint])}
      >
        {image}
      </div>
      <div className="flex flex-1 flex-col gap-[5px] p-3">
        {cert}
        <h3 className="text-[13.5px] font-extrabold leading-[1.3]">{title}</h3>
        <span className="text-[11.5px] text-sub">{brandLine}</span>
        <button
          type="button"
          className="mt-auto min-h-[44px] rounded-[10px] bg-brand p-2.5 text-center text-[12.5px] font-extrabold text-white"
        >
          {cta}
        </button>
      </div>
    </div>
  );
}
