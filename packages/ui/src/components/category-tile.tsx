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
 * (design-system.md §4). Renders an anchor when `href` is given, otherwise a
 * button (D09 language picker) - visual anatomy is identical either way.
 */
export function CategoryTile({
  icon,
  label,
  vernacular,
  tint,
  href,
  onClick,
  selected = false,
  soon = false,
  soonLabel = "Soon",
  className,
}: {
  icon: ReactNode;
  label: ReactNode;
  vernacular: ReactNode;
  tint: Tint;
  href?: string;
  onClick?: () => void;
  selected?: boolean;
  /** A-U1 `.tile.soon`: the vertical exists in the registry but its surface
   * has not shipped — the tile dims and carries a corner "Soon" chip. The
   * tile STAYS the link (to its honest coming-soon landing); the chip is
   * decorative (`aria-hidden`), the landing page says the same thing in
   * accessible text. */
  soon?: boolean;
  /** Translated chip text — the caller passes its locale's "Soon". */
  soonLabel?: ReactNode;
  className?: string;
}) {
  const classes = cn(
    "relative flex min-h-[104px] flex-col items-center justify-start gap-1.5 rounded-card border-[1.5px] border-line bg-card px-1.5 pb-2.5 pt-3 text-center text-ink no-underline",
    "transition-[transform,box-shadow,border-color] duration-100 hover:-translate-y-0.5 hover:border-brand hover:shadow-lift",
    "motion-reduce:transition-none motion-reduce:hover:translate-y-0",
    "max-sm:min-h-[98px] max-sm:px-1 max-sm:pb-2 max-sm:pt-2.5",
    selected && "border-brand ring-[3px] ring-accent",
    className,
  );
  const body = (
    <>
      {soon ? (
        // text-sub, not text-muted: 8.5px on cream-deep needs the darker
        // grey to clear AA (muted measures 4.47:1 here — axe).
        <span
          aria-hidden="true"
          className="absolute right-1.5 top-1.5 rounded-pill bg-cream-deep px-[7px] py-px text-[8.5px] font-medium text-sub"
        >
          {soonLabel}
        </span>
      ) : null}
      <span
        aria-hidden="true"
        className={cn(
          "flex h-[52px] w-[52px] items-center justify-center rounded-icon text-[30px] leading-none",
          "max-sm:h-[46px] max-sm:w-[46px] max-sm:text-[26px]",
          // The reference dims the WHOLE soon tile to .62, but blended text
          // fails AA (label lands at 4.4:1 — axe, AG-A9/A7 gates). Dim only
          // the decorative icon; the label keeps full opacity in the muted
          // ramp below. Recorded as an a11y-driven deviation in polish-a1.
          soon && "opacity-[.62]",
          tintClass[tint],
        )}
      >
        {icon}
      </span>
      <b className={cn("text-xs font-bold leading-[1.25]", soon && "text-sub")}>
        {label}
        <span className="vern text-[10.5px]">{vernacular}</span>
      </b>
    </>
  );
  if (href) {
    return (
      <a href={href} className={classes}>
        {body}
      </a>
    );
  }
  return (
    <button type="button" onClick={onClick} aria-pressed={selected} className={classes}>
      {body}
    </button>
  );
}
