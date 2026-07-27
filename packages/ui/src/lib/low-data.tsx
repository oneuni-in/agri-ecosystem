"use client";

import { useCallback, useSyncExternalStore } from "react";

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

export function LowDataToggle({ label }: { label: string }) {
  const on = useLowData();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      data-testid="low-data-toggle"
      onClick={() => setLowData(!on)}
      className="tap-target whitespace-nowrap text-[12px] font-bold text-sub"
    >
      {label}: {on ? "ON" : "OFF"}
    </button>
  );
}
