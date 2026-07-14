import type { ButtonHTMLAttributes } from "react";

import { cn } from "../lib/cn";

/** Unread badge text: hidden at 0, capped at 99+. */
export function formatUnread(count: number): string {
  if (count <= 0) return "";
  return count > 99 ? "99+" : String(count);
}

/**
 * Notification bell for HeaderStack's `right` slot (D12). Presentational:
 * data wiring lives in @agri/auth-client (NotificationBellIsland). Emoji
 * glyph per design-system icon convention; `rating` token for the badge
 * (amber - the palette ships no red).
 */
export function NotificationBell({
  unread = 0,
  label,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { unread?: number; label: string }) {
  const badge = formatUnread(unread);
  return (
    <button
      type="button"
      aria-label={badge ? `${label} (${badge})` : label}
      className={cn(
        "tap-target relative flex items-center justify-center rounded-pill border border-white/30 bg-glass px-3.5 py-[7px] text-[15px] text-white",
        className,
      )}
      {...props}
    >
      <span aria-hidden="true">🔔</span>
      {badge ? (
        <span
          aria-hidden="true"
          className="absolute -right-1 -top-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-pill bg-rating px-1 text-[11px] font-extrabold text-white"
        >
          {badge}
        </span>
      ) : null}
    </button>
  );
}
