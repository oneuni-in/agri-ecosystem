"use client";

import { useEffect } from "react";

/** Registers the PWA service worker (public/sw.js). Always on in production
 * builds; dev opt-in via NEXT_PUBLIC_ENABLE_SW=1 (the e2e servers run `next
 * dev`, where an always-on SW would fight HMR). */
export function SwRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    if (process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_ENABLE_SW !== "1") return;
    void navigator.serviceWorker.register("/sw.js");
  }, []);
  return null;
}
