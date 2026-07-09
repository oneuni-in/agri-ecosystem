import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/** Grid wrapper for big CTA tiles (`.bigcta`). */
export function BigCtaGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]", className)}>
      {children}
    </div>
  );
}

/**
 * Big CTA tile (`.bc`): brand gradient (140deg), white text, 32px icon,
 * glass "go" pill. Gradients are spec, not decoration — do not simplify.
 */
export function BigCtaTile({
  icon,
  title,
  sub,
  cta,
  href,
  gradient = "brand",
  className,
}: {
  icon: ReactNode;
  title: ReactNode;
  sub: ReactNode;
  cta: ReactNode;
  href: string;
  gradient?: "brand" | "gold";
  className?: string;
}) {
  return (
    <a
      href={href}
      className={cn(
        "flex flex-col gap-1.5 rounded-band p-5 text-white no-underline",
        gradient === "gold" ? "bg-gold-gradient" : "bg-cta-gradient",
        className,
      )}
    >
      <span aria-hidden="true" className="text-[32px] leading-none">
        {icon}
      </span>
      <b className="text-[17px]">{title}</b>
      <small className="text-[13px] opacity-90">{sub}</small>
      <span className="tap-target mt-2 self-start rounded-pill border border-white/40 bg-white/20 px-[18px] py-[9px] text-[13.5px] font-extrabold text-white">
        {cta}
      </span>
    </a>
  );
}
