"use client";

import { useEffect } from "react";

/**
 * Registers the single-purpose service worker (A-U3 W2).
 *
 * Mounted ONLY on /helplines, not in the root layout, and that placement
 * is the scope boundary: visiting the page is what opts a device into
 * caching the page. Nothing else on agri.in gains a worker, so A-U4's
 * PWA work starts from a clean slate rather than inheriting this.
 *
 * Silent on failure. A browser without service workers, or a user who
 * has blocked them, still gets a fully working online page — the worker
 * only ever adds the offline case.
 */
export function RegisterHelplineSW() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    // After load: registration competes with the page's own resources
    // otherwise, and this is the one page where first paint matters most.
    const register = () => {
      void navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    };
    if (document.readyState === "complete") register();
    else {
      window.addEventListener("load", register, { once: true });
      return () => window.removeEventListener("load", register);
    }
    return undefined;
  }, []);

  return null;
}
