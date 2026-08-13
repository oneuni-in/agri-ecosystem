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
  { href: "/", title: "Dashboard", icon: "🏠", sub: "Console home", roles: STAFF_UP },
  {
    href: "/ops",
    title: "Ops",
    icon: "🛠️",
    sub: "Moderation queues, flags & tiers",
    roles: STAFF_UP,
  },
  {
    href: "/businesses",
    title: "Businesses",
    icon: "🏪",
    sub: "Directory & enforcement",
    roles: STAFF_UP,
  },
  { href: "/ads", title: "Ads", icon: "📣", sub: "Creatives & campaigns", roles: STAFF_UP },
  { href: "/users", title: "Users", icon: "👤", sub: "Search & profiles", roles: STAFF_UP },
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
  return ADMIN_NAV.filter((item) => item.roles.some((role) => roles.includes(role)));
}
