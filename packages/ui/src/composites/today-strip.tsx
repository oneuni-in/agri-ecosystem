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

/**
 * A-U1 — the A1 `.tcard`, agri's Today card (sibling of milk's TodayCard
 * below; extending this file rather than forking, per the build prompt).
 * A link card: uppercase 10px label → 21px display value → 11.5px sub →
 * go-line. `tone="ask"` is the gradient Ask-agri.in card, with a solid
 * brand-deep underlay beneath the gradient (the AppBand axe/tw-merge
 * lesson: `cn()` would drop a `bg-*` color next to the gradient class, and
 * axe cannot read contrast through a background-image).
 */
export function TodayTile({
  label,
  value,
  sub,
  go,
  tone = "card",
  href,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  sub: ReactNode;
  /** The "7-day forecast →" line. Plain text — the whole tile is the link. */
  go?: ReactNode;
  tone?: "card" | "ask";
  href: string;
  className?: string;
}) {
  const ask = tone === "ask";
  return (
    <a
      href={href}
      className={cn(
        "relative flex flex-col gap-[3px] rounded-card border px-[15px] py-[13px] no-underline",
        ask
          ? "border-brand [background-color:var(--brand-deep)] bg-band-gradient text-white"
          : "border-cream-line bg-card",
        className,
      )}
    >
      <span
        className={cn(
          "text-[10px] font-medium uppercase tracking-[.06em]",
          ask ? "text-brand-soft-2" : "text-muted",
        )}
      >
        {label}
      </span>
      <span className="flex items-center gap-2 font-display text-[21px] font-semibold">
        {value}
      </span>
      <span className={cn("text-[11.5px]", ask ? "text-brand-soft" : "text-sub")}>{sub}</span>
      {go ? (
        <span className={cn("mt-1 text-[11.5px] font-medium", ask ? "text-coins-bg" : "text-brand")}>
          {go}
        </span>
      ) : null}
    </a>
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
