/**
 * /account module registry (AG-U5 P1) - THE mount contract.
 *
 * Deliberately the same shape as `console-modules.ts`, and for the same
 * reason: adding an account module means (1) create
 * `app/account/<module>/page.tsx`, (2) append ONE entry here, (3) add its
 * three strings under `ui.account.nav`. Never edit `app/account/layout.tsx`
 * for a new module - extend, not fork.
 *
 * WHAT THIS SHELL OWNS, AND WHAT IT DOES NOT.
 * The dashboard owns agri-side state: enquiries, price alerts, saved items,
 * the coins view, reviews and preferences. It does NOT own identity. Name,
 * handle, phone, avatar and language belong to AgriID, so the profile entry
 * is `external` and leaves for id.agri.in rather than growing an edit form
 * here - one profile, one place that writes it (A5's own sidebar footnote,
 * and AG-U5's out-of-bounds).
 *
 * WHY EVERY HREF IS UNDER /account.
 * `/coins`, `/saved` and `/notifications` shipped as top-level routes and
 * were moved here by owner decision at CP0. The move is only safe because
 * permanent redirects stay behind at the old paths - `notify/drivers.py`
 * hardcodes `/notifications` into every web-push payload on all four apps,
 * so that redirect is load-bearing, not a transition courtesy. The full
 * reasoning is in `docs/qa/ag-u5-drift.md` §3.1; `account-modules.test.ts`
 * holds the line.
 */

export interface AccountModule {
  /** Stable key: the i18n lookup (`ui.account.nav.<id>`) and the React key. */
  id: string;
  /** Internal path, or the path on the AgriID origin when `external`. */
  href: string;
  /** The sidebar's icon column (A5). Decorative - `aria-hidden` at render. */
  icon: string;
  /** Entries below the "Settings" divider. Must be contiguous and last. */
  group?: "settings";
  /** Renders as a plain anchor onto id.agri.in, not an in-app Link. */
  external?: true;
}

export const ACCOUNT_MODULES: AccountModule[] = [
  { id: "overview", href: "/account", icon: "🏠" },
  { id: "inquiries", href: "/account/inquiries", icon: "📩" },
  { id: "alerts", href: "/account/alerts", icon: "🔔" },
  { id: "saved", href: "/account/saved", icon: "🔖" },
  { id: "reviews", href: "/account/reviews", icon: "⭐" },
  { id: "coins", href: "/account/coins", icon: "🪙" },
  { id: "notifications", href: "/account/notifications", icon: "🔕", group: "settings" },
  { id: "profile", href: "/account", icon: "👤", group: "settings", external: true },
  { id: "devices", href: "/account/devices", icon: "📱", group: "settings" },
  { id: "privacy", href: "/account/privacy", icon: "🔒", group: "settings" },
];

/**
 * The href to actually render.
 *
 * `idOrigin` is passed in rather than read from `process.env` here so the
 * layout resolves it once on the server and the value is testable without
 * mutating the environment.
 */
export function resolveModuleHref(entry: AccountModule, idOrigin: string): string {
  if (!entry.external) return entry.href;
  return `${idOrigin.replace(/\/+$/, "")}${entry.href}`;
}
