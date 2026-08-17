import { getTranslations } from "next-intl/server";
import Link from "next/link";

/**
 * A1 §23 — mobile bottom nav: Home · Mandi · Ask (raised mic) · Alerts ·
 * Profile. Fixed, 64px plus the iOS safe-area inset, hidden from `md` up;
 * the body reserves matching padding in `layout.tsx` (milk's §12 lesson —
 * without it the last footer row sits under the bar).
 *
 * Link targets, honest-today edition:
 *   · Home    → "/" (aria-current)
 *   · Mandi   → /#mandi — the §7 mandi-cards anchor (real since CP3; when
 *               the flag is off the anchor scrolls to top, still honest)
 *   · Ask     → /#ask — the §12 Ask band's anchor on this page
 *   · Alerts  → /notifications (real)
 *   · Profile → /account/inquiries — the only account surface web-agri has
 *               today (there is no /account index route)
 */
export async function AgriBottomNav() {
  const t = await getTranslations("ui");
  const left = [
    { href: "/", icon: "🏠", label: t("nav.home"), active: true },
    { href: "/#mandi", icon: "📈", label: t("agriHome.nav.mandi"), active: false },
  ];
  const right = [
    { href: "/notifications", icon: "🔔", label: t("nav.alerts"), active: false },
    { href: "/account/inquiries", icon: "👤", label: t("nav.profile"), active: false },
  ];
  return (
    <nav
      aria-label={t("nav.home")}
      data-testid="agri-bottom-nav"
      className="fixed inset-x-0 bottom-0 z-50 flex h-[calc(64px+env(safe-area-inset-bottom))] items-center border-t border-cream-line bg-card pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {left.map((item) => (
        <NavItem key={item.href} {...item} />
      ))}
      <Link
        href="/#ask"
        prefetch={false}
        aria-label={t("agriHome.nav.ask")}
        className="-mt-5 flex h-[46px] w-[46px] flex-none items-center justify-center rounded-pill border-[3px] border-cream bg-brand text-[19px] text-white no-underline"
      >
        <span aria-hidden="true">🎙️</span>
      </Link>
      {right.map((item) => (
        <NavItem key={item.href} {...item} />
      ))}
    </nav>
  );
}

function NavItem({
  href,
  icon,
  label,
  active,
}: {
  href: string;
  icon: string;
  label: string;
  active: boolean;
}) {
  // min-h 44: the LINK is the tap target, not the 64px bar (milk's §1.5 fix).
  return (
    <Link
      href={href}
      prefetch={false}
      {...(active ? { "aria-current": "page" as const } : {})}
      className={`flex min-h-[44px] flex-1 flex-col items-center justify-center text-[10px] no-underline ${
        active ? "text-brand" : "text-sub"
      }`}
    >
      <span aria-hidden="true" className="text-[19px] leading-none">
        {icon}
      </span>
      {label}
    </Link>
  );
}
