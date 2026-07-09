import type { ReactNode } from "react";

import { cn } from "../lib/cn";

export type Tint =
  | "green"
  | "sand"
  | "blush"
  | "peach"
  | "bluegray"
  | "aqua"
  | "cream"
  | "lilac"
  | "gold"
  | "violet"
  | "stone"
  | "mist"
  | "sky"
  | "blue"
  | "leaf"
  | "sage"
  | "fern";

/** Literal class names so Tailwind's content scanner sees them. */
export const tintClass: Record<Tint, string> = {
  green: "bg-tint-green",
  sand: "bg-tint-sand",
  blush: "bg-tint-blush",
  peach: "bg-tint-peach",
  bluegray: "bg-tint-bluegray",
  aqua: "bg-tint-aqua",
  cream: "bg-tint-cream",
  lilac: "bg-tint-lilac",
  gold: "bg-tint-gold",
  violet: "bg-tint-violet",
  stone: "bg-tint-stone",
  mist: "bg-tint-mist",
  sky: "bg-tint-sky",
  blue: "bg-tint-blue",
  leaf: "bg-tint-leaf",
  sage: "bg-tint-sage",
  fern: "bg-tint-fern",
};

/**
 * Icon + English + mother tongue on every tile (UX law 1). Emoji icons are
 * v1-official; a custom icon set later swaps in behind the `icon` prop
 * (design-system.md §4).
 */
export function CategoryTile({
  icon,
  label,
  vernacular,
  tint,
  href,
  className,
}: {
  icon: ReactNode;
  label: ReactNode;
  vernacular: ReactNode;
  tint: Tint;
  href: string;
  className?: string;
}) {
  return (
    <a
      href={href}
      className={cn(
        "flex min-h-[104px] flex-col items-center justify-start gap-1.5 rounded-card border-[1.5px] border-line bg-card px-1.5 pb-2.5 pt-3 text-center text-ink no-underline",
        "transition-[transform,box-shadow,border-color] duration-100 hover:-translate-y-0.5 hover:border-brand hover:shadow-lift",
        "motion-reduce:transition-none motion-reduce:hover:translate-y-0",
        "max-sm:min-h-[98px] max-sm:px-1 max-sm:pb-2 max-sm:pt-2.5",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "flex h-[52px] w-[52px] items-center justify-center rounded-icon text-[30px] leading-none",
          "max-sm:h-[46px] max-sm:w-[46px] max-sm:text-[26px]",
          tintClass[tint],
        )}
      >
        {icon}
      </span>
      <b className="text-xs font-bold leading-[1.25]">
        {label}
        <span className="vern text-[10.5px]">{vernacular}</span>
      </b>
    </a>
  );
}
