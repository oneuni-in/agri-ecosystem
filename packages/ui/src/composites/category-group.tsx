import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * Category group (`.catgroup-t` + `.catgrid`): uppercase hairline label +
 * auto-fill grid. All categories on the homepage, zero hamburgers (UX law 2).
 */
export function CategoryGroup({
  label,
  children,
  className,
}: {
  label: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="mb-2.5 mt-[18px] flex items-center gap-2 text-[13px] font-extrabold uppercase tracking-[.05em] text-sub after:h-px after:flex-1 after:bg-line after:content-['']">
        {label}
      </div>
      <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fill,minmax(96px,1fr))] max-sm:grid-cols-4">
        {children}
      </div>
    </div>
  );
}
