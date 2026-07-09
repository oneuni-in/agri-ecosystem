import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/** Page gutter (`.wrap`): 1140px centered column. */
export function Wrap({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto max-w-[1140px] px-4", className)}>{children}</div>;
}

/** Section with heading row (`.sec` / `.sec-t`). */
export function Section({
  title,
  see,
  seeHref,
  children,
  className,
}: {
  title: ReactNode;
  see?: ReactNode;
  seeHref?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("pb-2 pt-[22px]", className)}>
      <div className="mb-3.5 flex items-baseline justify-between gap-2.5">
        <h2 className="font-display text-xl font-extrabold">{title}</h2>
        {see ? (
          <a href={seeHref ?? "#"} className="text-[13px] font-bold text-brand-deep no-underline">
            {see}
          </a>
        ) : null}
      </div>
      {children}
    </section>
  );
}

/** Listing-card grid (`.cards-row`): auto-fill minmax(250px,1fr). */
export function CardsRow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(250px,1fr))]", className)}>
      {children}
    </div>
  );
}
