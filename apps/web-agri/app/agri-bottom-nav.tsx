import { getTranslations } from "next-intl/server";

import { AgriBottomNavLinks, type BottomNavItem } from "./agri-bottom-nav-links";

/**
 * A1 §23 — mobile bottom nav: Home · Mandi · Ask (raised mic) · Alerts ·
 * Profile. Fixed, 64px plus the iOS safe-area inset, hidden from `md` up;
 * the body reserves matching padding in `layout.tsx` (milk's §12 lesson —
 * without it the last footer row sits under the bar).
 *
 * Link targets:
 *   · Home    → "/" (the only exact-match tab)
 *   · Mandi   → /#mandi — the §7 mandi-cards anchor
 *   · Ask     → /#ask — the §12 Ask band's anchor on this page
 *   · Alerts  → /account/notifications
 *   · Profile → /account — the dashboard shell (AG-U5 P1)
 *
 * AG-U5 P1 also made the highlight real. It used to be a hardcoded
 * `active: true` on Home, so Home stayed lit while you stood on the
 * notifications page; `activeNavHref` now picks the longest matching target,
 * which is what lets Alerts and Profile coexist when one nests under the
 * other. The list is defined here (a Server Component, for the translations)
 * and handed to a client island that reads the pathname.
 */
export async function AgriBottomNav() {
  const t = await getTranslations("ui");
  const items: BottomNavItem[] = [
    { href: "/", icon: "🏠", label: t("nav.home") },
    { href: "/#mandi", icon: "📈", label: t("agriHome.nav.mandi") },
    { href: "/account/notifications", icon: "🔔", label: t("nav.alerts") },
    { href: "/account", icon: "👤", label: t("nav.profile") },
  ];
  return (
    <AgriBottomNavLinks
      navLabel={t("nav.home")}
      items={items}
      askHref="/#ask"
      askLabel={t("agriHome.nav.ask")}
    />
  );
}
