"use client";

import { useCallback, useSyncExternalStore } from "react";

import { cn } from "./cn";
import { lowDataCookieString, parseLowDataCookie } from "./low-data-core";

const listeners = new Set<() => void>();

function read(): boolean {
  if (typeof document === "undefined") return false;
  const connection = (navigator as { connection?: { saveData?: boolean } }).connection;
  return parseLowDataCookie(document.cookie, connection?.saveData === true);
}

export function setLowData(on: boolean): void {
  document.cookie = lowDataCookieString(on);
  listeners.forEach((listener) => listener());
}

/** Data-saver preference (D28): explicit cookie wins, else the browser's
 * Save-Data signal. SSR snapshot is always false (ISR pages must not vary
 * on cookies) — consumers apply the saving behavior client-side. */
export function useLowData(): boolean {
  return useSyncExternalStore(
    useCallback((onStoreChange: () => void) => {
      listeners.add(onStoreChange);
      return () => listeners.delete(onStoreChange);
    }, []),
    read,
    () => false,
  );
}

export function LowDataToggle({
  label,
  onLabel = "ON",
  offLabel = "OFF",
  className,
}: {
  label: string;
  /** Lets a host restyle the toggle for its surface. It defaults to --sub,
   * which is a light-background colour: on a dark footer that measures
   * 1.55:1, so a dark host MUST pass a light class here. */
  className?: string;
  /** Translated state words — the toggle sits in the footer of a fully
   * localised page, so "ON"/"OFF" must not stay English there. */
  onLabel?: string;
  offLabel?: string;
}) {
  const on = useLowData();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      data-testid="low-data-toggle"
      onClick={() => setLowData(!on)}
      className={cn("tap-target whitespace-nowrap text-[12px] font-bold text-sub", className)}
    >
      {label}: {on ? onLabel : offLabel}
    </button>
  );
}
