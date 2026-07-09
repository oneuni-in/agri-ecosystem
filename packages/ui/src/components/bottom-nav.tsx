import type { ReactNode } from "react";

import { cn } from "../lib/cn";

export interface BottomNavItem {
  icon: ReactNode;
  label: ReactNode;
  href?: string;
  active?: boolean;
  /** Center "Ask AI" slot — 46px brand circle raised −22px with 4px white ring. */
  ai?: boolean;
}

/**
 * 5-slot sticky bottom nav (`.appnav`). Voice is first-class: Ask AI is the
 * raised center button (UX law 3).
 */
export function BottomNav({ items, className }: { items: BottomNavItem[]; className?: string }) {
  return (
    <nav
      className={cn(
        "sticky bottom-0 z-[60] flex justify-around border-t border-line bg-card px-1 pb-2.5 pt-2 shadow-nav",
        className,
      )}
    >
      {items.map((item, i) => {
        const itemClasses = cn(
          "flex min-h-[44px] min-w-[60px] flex-col items-center gap-0.5 text-[10.5px] font-bold text-sub no-underline",
          item.active && "text-brand-deep",
        );
        const icon = item.ai ? (
          <span
            aria-hidden="true"
            className="mt-[-22px] flex h-[46px] w-[46px] items-center justify-center rounded-full border-4 border-card bg-brand text-[21px] leading-none text-white shadow-ai"
          >
            {item.icon}
          </span>
        ) : (
          <span aria-hidden="true" className="text-[21px] leading-none">
            {item.icon}
          </span>
        );
        return item.href ? (
          <a key={i} href={item.href} className={itemClasses}>
            {icon}
            {item.label}
          </a>
        ) : (
          <button key={i} type="button" className={itemClasses}>
            {icon}
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}
