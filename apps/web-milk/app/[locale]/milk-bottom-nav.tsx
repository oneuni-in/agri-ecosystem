import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";

/**
 * §12 — mobile bottom nav. Fixed, 64px plus the iOS safe-area inset, hidden
 * from `md` up. The body gets matching bottom padding (see `[locale]/layout`)
 * so the footer clears it and stays fully visible — the reference is explicit
 * about that, and without it the last footer row sits under the bar.
 *
 * The centre mic routes into the D25 voice-first post-need flow; it is a door
 * to the existing route, not a capture surface of its own.
 */
export async function MilkBottomNav() {
  const t = await getTranslations("ui.nav");
  const items = [
    { href: "/", icon: "🏠", label: t("home"), active: true },
    { href: "/search", icon: "🗂️", label: t("categories"), active: false },
    { href: "/notifications", icon: "🔔", label: t("alerts"), active: false },
    { href: "/my-needs", icon: "👤", label: t("profile"), active: false },
  ];
  return (
    <nav
      aria-label={t("home")}
      data-testid="milk-bottom-nav"
      className="fixed inset-x-0 bottom-0 z-50 flex h-[calc(64px+env(safe-area-inset-bottom))] items-center border-t border-cream-line bg-card pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {items.slice(0, 2).map((item) => (
        <NavItem key={item.href} {...item} />
      ))}
      <Link
        href="/post-need"
        prefetch={false}
        aria-label={t("askAi")}
        className="-mt-5 flex h-[46px] w-[46px] flex-none items-center justify-center rounded-pill border-[3px] border-cream bg-brand text-[19px] text-white no-underline"
      >
        <span aria-hidden="true">🎙️</span>
      </Link>
      {items.slice(2).map((item) => (
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
  return (
    <Link
      href={href}
      prefetch={false}
      {...(active ? { "aria-current": "page" as const } : {})}
      // min-h 44: the icon+label column measured ~34px, under the §1.5 tap
      // floor even though the bar itself is 64px — the LINK is the target,
      // not the bar. justify-center keeps the column centred in the new box.
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
