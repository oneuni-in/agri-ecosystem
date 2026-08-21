/**
 * The admin module catalog — ONE list feeding the shell nav and the dashboard
 * tiles, so a surface cannot appear in one and not the other.
 *
 * `roles` mirrors what the backend actually enforces today (the BFF only
 * mints sessions for staff/super_admin at all; coins WRITES are
 * super_admin-only per D13's coins admin_router). This is presentation
 * gating on top of API enforcement, never instead of it — every management
 * endpoint rejects below the required role regardless of what the UI shows.
 * When RBAC v2 lands its grant matrix, `roles` here becomes permission keys
 * resolved server-side; the filtering seam (`navFor`) stays.
 */
export interface AdminNavItem {
  href: string;
  title: string;
  icon: string;
  sub: string;
  roles: readonly string[];
}

const STAFF_UP = ["staff", "super_admin"] as const;

export const ADMIN_NAV: readonly AdminNavItem[] = [
  {
    href: "/",
    title: "Dashboard",
    icon: "🏠",
    sub: "Console home",
    roles: STAFF_UP,
  },
  {
    href: "/ops",
    title: "Ops",
    icon: "🛠️",
    sub: "Moderation queues, flags & tiers",
    roles: STAFF_UP,
  },
  {
    href: "/content",
    title: "Content",
    icon: "📰",
    sub: "Review & publish news, guides, advisories",
    roles: STAFF_UP,
  },
  {
    href: "/directory",
    title: "Directory",
    icon: "🏪",
    sub: "Browse & enforce all listings",
    roles: STAFF_UP,
  },
  {
    href: "/businesses",
    title: "Enforcement lookup",
    icon: "🔎",
    sub: "One business by slug + audit log",
    roles: STAFF_UP,
  },
  {
    href: "/ads",
    title: "Ads",
    icon: "📣",
    sub: "Creatives & campaigns",
    roles: STAFF_UP,
  },
  {
    href: "/ad-performance",
    title: "Ad performance",
    icon: "📈",
    sub: "Impressions, clicks & CTR",
    roles: STAFF_UP,
  },
  {
    href: "/users",
    title: "Users",
    icon: "👤",
    sub: "Search & profiles",
    roles: STAFF_UP,
  },
  {
    href: "/payments",
    title: "Payments",
    icon: "🧾",
    sub: "Razorpay ledger (read-only)",
    roles: STAFF_UP,
  },
  {
    href: "/tiers",
    title: "Pincode tiers",
    icon: "🗺️",
    sub: "T1–T5 with census inputs",
    roles: STAFF_UP,
  },
  {
    href: "/data-requests",
    title: "Data requests",
    icon: "🗂️",
    sub: "DPDP export & erasure queue",
    roles: STAFF_UP,
  },
  {
    href: "/audit",
    title: "Audit log",
    icon: "📜",
    sub: "Append-only timeline (read-only)",
    roles: STAFF_UP,
  },
  {
    href: "/coins",
    title: "Coins",
    icon: "🪙",
    sub: "Rules & adjustments",
    roles: ["super_admin"],
  },
];

/** The role-gated filter the shell and dashboard both render from. */
export function navFor(roles: readonly string[]): readonly AdminNavItem[] {
  return ADMIN_NAV.filter((item) =>
    item.roles.some((role) => roles.includes(role)),
  );
}
