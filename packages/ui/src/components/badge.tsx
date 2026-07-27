import type { ReactNode } from "react";

import { cn } from "../lib/cn";

const base = "inline-flex items-center gap-1 self-start rounded-pill px-[9px] py-[3px] text-[11px] font-extrabold";

type BadgeProps =
  /** Sponsored is ALWAYS labeled "★ Sponsored" (UX law 5) — no children accepted. */
  | { variant: "sponsored"; children?: never; className?: string }
  | { variant: "verified" | "cert" | "neutral"; children: ReactNode; className?: string };

export function Badge(props: BadgeProps) {
  if (props.variant === "sponsored") {
    return (
      <span className={cn(base, "bg-sponsored-bg text-sponsored-fg", props.className)}>
        ★ Sponsored
      </span>
    );
  }
  // `neutral` isn't in the mockup (only verified/sponsored/cert are) - built
  // from existing shared tokens per design-system.md's extension rule
  // ("never invent a new visual language"): outlined card/line/sub instead
  // of a filled pastel, so a plain label (e.g. a non-dairy category name on
  // the D27 brand/vendor page) can never be mistaken for a trust badge.
  const palette =
    props.variant === "verified"
      ? "bg-verified-bg text-verified-fg"
      : props.variant === "cert"
        ? "bg-cert-bg text-cert-fg"
        : "border border-line bg-card text-sub";
  return <span className={cn(base, palette, props.className)}>{props.children}</span>;
}
