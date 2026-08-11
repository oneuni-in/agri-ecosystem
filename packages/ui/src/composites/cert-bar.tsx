import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * Cert trust bar (`.certbar`): horizontal scroll cards.
 *
 * `tabIndex={0}` because the cards are static content with nothing focusable
 * inside: a scrollable region that cannot be reached by keyboard is a serious
 * axe violation (`scrollable-region-focusable`) and, more to the point, a
 * keyboard user could not read the cards past the fold on a phone.
 */
export function CertBar({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div tabIndex={0} className={cn("flex gap-2.5 overflow-x-auto pb-1.5", className)}>
      {children}
    </div>
  );
}

/**
 * `.certcard`; the "We verify every certificate" card gets the gold
 * treatment (`gold` prop).
 */
export function CertCard({
  icon,
  title,
  sub,
  gold = false,
  className,
}: {
  icon: ReactNode;
  title: ReactNode;
  sub: ReactNode;
  gold?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-w-[230px] shrink-0 items-center gap-2.5 rounded-icon border-[1.5px] border-line bg-card px-4 py-3",
        gold && "border-certgold-line bg-certgold-bg",
        className,
      )}
    >
      <span aria-hidden="true" className="text-[26px] leading-none">
        {icon}
      </span>
      <div>
        <b className="block text-[13.5px]">{title}</b>
        <small className="text-[11.5px] text-sub">{sub}</small>
      </div>
    </div>
  );
}
