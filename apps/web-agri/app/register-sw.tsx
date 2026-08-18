"use client";

import { useEffect } from "react";

/**
 * A-U4 W4 — registers the service worker for the whole site.
 *
 * A-U3 mounted this on /helplines alone and said so explicitly: visiting
 * that page was what opted a device into caching, so "A-U4's PWA work starts
 * from a clean slate rather than inheriting this". This is A-U4 taking that
 * slate — one registration, in the root layout, for one worker.
 *
 * Still exactly ONE worker and one scope. The worker decides what to cache
 * (see public/sw.js); this only decides that it exists.
 *
 * Silent on failure. A browser without service workers, or a user who has
 * blocked them, still gets a fully working online site — the worker only
 * ever adds the offline case.
 */
export function RegisterSW() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    // After load: registration competes with the page's own resources
    // otherwise, and first paint is the thing W0 spent a whole work package
    // protecting.
    const register = () => {
      void navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    };
    if (document.readyState === "complete") {
      register();
      return undefined;
    }
    window.addEventListener("load", register, { once: true });
    return () => window.removeEventListener("load", register);
  }, []);

  return null;
}
