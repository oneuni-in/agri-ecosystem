"use client";

/**
 * The bottom bar's links, as a client island (AG-U5 P1).
 *
 * Only this list is client-side; `agri-bottom-nav.tsx` stays a Server
 * Component so the labels come from the server catalog and no translation
 * payload is shipped for them. The island exists purely because the active
 * tab depends on the pathname, which a Server Component cannot read — the
 * same split `business/console-nav-links.tsx` makes for the sidebar.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import { activeNavHref } from "@/lib/nav-active";

export interface BottomNavItem {
  href: string;
  icon: string;
  label: string;
}

export function AgriBottomNavLinks({
  navLabel,
  items,
  askHref,
  askLabel,
}: {
  navLabel: string;
  items: BottomNavItem[];
  askHref: string;
  askLabel: string;
}) {
  const pathname = usePathname();
  const active = activeNavHref(
    pathname,
    items.map((item) => item.href),
  );
  // The raised mic sits in the middle of the bar, so the items split around
  // it rather than rendering as one list.
  const half = Math.ceil(items.length / 2);

  return (
    <nav
      aria-label={navLabel}
      data-testid="agri-bottom-nav"
      className="fixed inset-x-0 bottom-0 z-50 flex h-[calc(64px+env(safe-area-inset-bottom))] items-center border-t border-cream-line bg-card pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {items.slice(0, half).map((item) => (
        <NavItem key={item.href} {...item} active={item.href === active} />
      ))}
      <Link
        href={askHref}
        prefetch={false}
        aria-label={askLabel}
        className="-mt-5 flex h-[46px] w-[46px] flex-none items-center justify-center rounded-pill border-[3px] border-cream bg-brand text-[19px] text-white no-underline"
      >
        <span aria-hidden="true">🎙️</span>
      </Link>
      {items.slice(half).map((item) => (
        <NavItem key={item.href} {...item} active={item.href === active} />
      ))}
    </nav>
  );
}

function NavItem({
  href,
  icon,
  label,
  active,
}: BottomNavItem & {
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
