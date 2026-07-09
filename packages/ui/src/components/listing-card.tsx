import type { ReactNode } from "react";

import { cn } from "../lib/cn";
import { Card } from "./card";
import { tintClass, type Tint } from "./category-tile";

/**
 * Vendor/listing card (`.card.lc`): badge row → 56px tinted icon square +
 * 15.5/800 title + meta → optional price-tag → action row.
 * Call/WhatsApp lead the action row — forms never do (UX law 4).
 */
export function ListingCard({
  badge,
  icon,
  tint,
  title,
  meta,
  priceTag,
  extraMeta,
  actions,
  className,
}: {
  badge?: ReactNode;
  icon: ReactNode;
  tint: Tint;
  title: ReactNode;
  meta: ReactNode;
  priceTag?: ReactNode;
  extraMeta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("flex flex-col gap-2 p-4", className)}>
      {badge}
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className={cn(
            "flex h-14 w-14 shrink-0 items-center justify-center rounded-icon text-[26px] leading-none",
            tintClass[tint],
          )}
        >
          {icon}
        </span>
        <div>
          <h3 className="text-[15.5px] font-extrabold leading-[1.3]">{title}</h3>
          <div className="text-[12.5px] text-sub">{meta}</div>
        </div>
      </div>
      {priceTag ? <div className="text-[15px] font-extrabold">{priceTag}</div> : null}
      {extraMeta ? <div className="text-[12.5px] text-sub">{extraMeta}</div> : null}
      {actions ? <div className="mt-1 flex gap-2">{actions}</div> : null}
    </Card>
  );
}

/** Muted unit suffix inside a price-tag: `₹55/L <PriceUnit>cow</PriceUnit>`. */
export function PriceUnit({ children }: { children: ReactNode }) {
  return <small className="text-[12.5px] font-semibold text-sub">{children}</small>;
}
