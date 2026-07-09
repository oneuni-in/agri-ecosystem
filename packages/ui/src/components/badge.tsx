import type { ReactNode } from "react";

import { cn } from "../lib/cn";

const base = "inline-flex items-center gap-1 self-start rounded-pill px-[9px] py-[3px] text-[11px] font-extrabold";

type BadgeProps =
  /** Sponsored is ALWAYS labeled "★ Sponsored" (UX law 5) — no children accepted. */
  | { variant: "sponsored"; children?: never; className?: string }
  | { variant: "verified" | "cert"; children: ReactNode; className?: string };

export function Badge(props: BadgeProps) {
  if (props.variant === "sponsored") {
    return (
      <span className={cn(base, "bg-sponsored-bg text-sponsored-fg", props.className)}>
        ★ Sponsored
      </span>
    );
  }
  const palette =
    props.variant === "verified"
      ? "bg-verified-bg text-verified-fg"
      : "bg-cert-bg text-cert-fg";
  return <span className={cn(base, palette, props.className)}>{props.children}</span>;
}
