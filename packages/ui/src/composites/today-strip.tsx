import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/** "Today" strip (`.myday`): auto-fit minmax(170px,1fr) cards. */
export function TodayStrip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(170px,1fr))]", className)}>
      {children}
    </div>
  );
}

/** `.md-card`: uppercase 11px/800 label row w/ emoji → 19px bold value → 12.5px sub. */
export function TodayCard({
  label,
  value,
  sub,
  alert = false,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  sub: ReactNode;
  /** Alert variant uses the alert palette (`.md-card.alert`). */
  alert?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-card border border-line bg-card px-4 py-3.5",
        alert && "border-alert-line bg-alert-bg",
        className,
      )}
    >
      <span className="flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-[.06em] text-sub">
        {label}
      </span>
      <b className="mt-[3px] block text-[19px]">{value}</b>
      <small className="text-[12.5px] text-sub">{sub}</small>
    </div>
  );
}
