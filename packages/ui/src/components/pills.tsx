import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "../lib/cn";

type PillButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

/** Glass pill on the header gradient (`.loc-pill` / `.lang-pill`). */
// `whitespace-nowrap`: below `sm` the location pill drops its label and is
// left with just "📍 ▾", narrow enough that the two glyphs wrapped onto two
// lines and rendered the pill as a squashed circle in a single-row header.
const glass =
  "tap-target flex items-center gap-1.5 whitespace-nowrap rounded-pill border border-white/30 bg-glass px-3.5 py-[7px] text-[13px] font-semibold text-white";

export function LocationPill({ className, children, ...props }: PillButtonProps) {
  return (
    <button type="button" className={cn(glass, className)} {...props}>
      {children}
    </button>
  );
}

export function LangSwitcher({
  label = "🌐 EN · த · हि",
  className,
  ...props
}: PillButtonProps & { label?: ReactNode }) {
  return (
    <button type="button" className={cn(glass, className)} {...props}>
      {label}
    </button>
  );
}

/** "Use my location" pill under the pincode hero (`.gps`). */
export function GpsPill({ className, children, ...props }: PillButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        "tap-target mt-2.5 inline-flex items-center gap-[7px] rounded-pill border border-white/35 bg-glass px-[18px] py-[9px] text-[13.5px] font-bold text-white",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

/** AgriCoins pill — the same gold pill on all three sites' headers (`.coins`). */
export function CoinsPill({
  amount,
  className,
  ...props
}: PillButtonProps & { amount: string | number }) {
  return (
    <button
      type="button"
      className={cn(
        "tap-target flex items-center gap-[5px] rounded-pill bg-coins-bg px-[13px] py-[7px] text-[13px] font-extrabold text-coins-fg",
        className,
      )}
      {...props}
    >
      🪙 {amount}
    </button>
  );
}

/** 38px white profile circle in the topbar (`.avatar`). */
export function Avatar({ initial, className, ...props }: PillButtonProps & { initial: string }) {
  return (
    <button
      type="button"
      className={cn(
        "tap-target flex h-[38px] w-[38px] items-center justify-center rounded-full bg-card text-[15px] font-extrabold text-ink",
        className,
      )}
      {...props}
    >
      {initial}
    </button>
  );
}
