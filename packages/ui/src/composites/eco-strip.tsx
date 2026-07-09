import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/** Ecosystem strip (`.ecostrip`): gradient pills linking sibling platforms. */
export function EcoStrip({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("flex gap-2.5 overflow-x-auto pb-4 pt-1", className)}>{children}</div>;
}

const gradients = {
  milk: "bg-eco-milk",
  organic: "bg-eco-organic",
  coins: "bg-eco-coins",
} as const;

/** `.eco-pill` — cross-site gradients are fixed tokens, not theme-dependent. */
export function EcoPill({
  title,
  sub,
  href,
  gradient,
  className,
}: {
  title: ReactNode;
  sub: ReactNode;
  href: string;
  gradient: keyof typeof gradients;
  className?: string;
}) {
  return (
    <a
      href={href}
      className={cn(
        "min-w-[210px] shrink-0 rounded-card px-[18px] py-3.5 text-white no-underline",
        gradients[gradient],
        className,
      )}
    >
      <b className="block font-display text-[17px] font-extrabold">{title}</b>
      <small className="text-xs opacity-90">{sub}</small>
    </a>
  );
}
