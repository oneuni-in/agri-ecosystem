import { auth } from "@/lib/auth";
import { CONSOLE_MODULES } from "@/lib/console-modules";

import { ConsoleNavLinks } from "./console-nav-links";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** billing_enabled probe: the backend 404s the whole /billing surface while
 * dark, so one status check lights (or hides) the billing module. */
async function billingVisible(): Promise<boolean> {
  const token = await auth.getAccessToken();
  if (!token) return false;
  try {
    const response = await fetch(`${API}/billing/subscription`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return response.status !== 404;
  } catch {
    return false;
  }
}

/** ads_enabled probe: the backend 404s the whole /ads/my surface while
 * dark, so one status check lights (or hides) the ads module. */
async function adsVisible(): Promise<boolean> {
  const token = await auth.getAccessToken();
  if (!token) return false;
  try {
    const response = await fetch(`${API}/ads/my/campaigns?limit=1`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return response.status !== 404;
  } catch {
    return false;
  }
}

export default async function BusinessConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // No auth gate here on purpose: every /business/* page.tsx already does
  // its own `if (!user) redirect("/api/auth/login?next=/business/<page>")`
  // with the CORRECT next path. A layout-level gate ran first (layouts
  // render before their page) and always redirected with next=/business -
  // a route with no page.tsx of its own - so a guest opening any console
  // page directly (bookmark, shared link, or Task 17's e2e login) landed on
  // a 404 after signing in. Removing the redundant, wrong-next gate here
  // lets the page-level redirect (the one with the real destination) win.
  const [showBilling, showAds] = await Promise.all([billingVisible(), adsVisible()]);
  const modules = CONSOLE_MODULES.filter((entry) => {
    if (entry.gate === "billing") return showBilling;
    if (entry.gate === "ads") return showAds;
    return true;
  });
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-6 sm:flex-row sm:gap-6">
      {/*
       * M5 Task 16 responsive fix: below `sm:` the fixed `w-48` sidebar left
       * ~127px of content at 375px (fails the mobile-usable DoD). Per the
       * design system's UX law #2 (nothing hidden behind a hamburger), the
       * SAME module list becomes a horizontally scrollable pill row above
       * the content instead - one <nav>, responsive classes only, no
       * separate mobile/desktop components. `sm:` and up reproduces the
       * original sidebar classes exactly (w-48 shrink-0 column list).
       */}
      <nav
        aria-label="Business console"
        className="flex gap-2 overflow-x-auto pb-1 sm:block sm:w-48 sm:shrink-0 sm:overflow-visible sm:pb-0"
      >
        <p className="hidden font-display text-[13px] font-extrabold uppercase tracking-wide text-sub sm:mb-3 sm:block">
          Business console
        </p>
        <ConsoleNavLinks modules={modules} />
      </nav>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
