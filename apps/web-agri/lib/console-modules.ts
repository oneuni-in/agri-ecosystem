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
 */
export type ConsoleGate = "billing";

export interface ConsoleModule {
  id: string;
  title: string;
  href: string;
  gate?: ConsoleGate;
}

export const CONSOLE_MODULES: ConsoleModule[] = [
  { id: "inbox", title: "Lead inbox", href: "/business/inbox" },
  { id: "listings", title: "Listings", href: "/business/listings" },
  { id: "products", title: "Products", href: "/business/products" },
  { id: "billing", title: "Subscription & invoices", href: "/business/billing", gate: "billing" },
];
