/**
 * Business Console module registry (D20) - THE mount contract.
 *
 * Adding a console module (D15 listings, D17 products, D18 inbox, future
 * specs) means: (1) create app/business/<module>/page.tsx, (2) append ONE
 * entry here. Never edit app/business/layout.tsx for a new module - extend,
 * not fork (the AuthCluster lesson applied to dashboards).
 *
 * `gate: "billing"` hides the entry while the billing_enabled backend flag
 * is off (the layout probes GET /billing/subscription; 404 = dark).
 * `gate: "ads"` hides the entry while the ads_enabled backend flag is off
 * (the layout probes GET /ads/my/campaigns?limit=1; 404 = dark).
 */
export type ConsoleGate = "billing" | "ads";

export interface ConsoleModule {
  id: string;
  title: string;
  href: string;
  gate?: ConsoleGate;
  /** A-U7: the sidebar glyph (A3 reference `.side nav a .ic`). Chrome, not
   * data — it lives on the registry entry so the nav and the dashboard's
   * module cards cannot drift into two different icons for one module. */
  icon: string;
}

export const CONSOLE_MODULES: ConsoleModule[] = [
  { id: "dashboard", title: "Dashboard", href: "/business", icon: "📊" },
  { id: "inbox", title: "Lead inbox", href: "/business/inbox", icon: "📥" },
  { id: "reviews", title: "Reviews", href: "/business/reviews", icon: "⭐" },
  { id: "listings", title: "Listings", href: "/business/listings", icon: "🏪" },
  { id: "products", title: "Products", href: "/business/products", icon: "📦" },
  {
    id: "notifications",
    title: "Notifications",
    href: "/business/notifications",
    icon: "🔔",
  },
  { id: "analytics", title: "Analytics", href: "/business/analytics", icon: "📈" },
  { id: "premium", title: "Premium", href: "/business/premium", icon: "💎" },
  {
    id: "billing",
    title: "Subscription & invoices",
    href: "/business/billing",
    gate: "billing",
    icon: "🧾",
  },
  { id: "ads", title: "Advertise", href: "/business/ads", gate: "ads", icon: "📣" },
];
