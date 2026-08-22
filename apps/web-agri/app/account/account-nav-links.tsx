"use client";

/**
 * Pathname-aware active state for the /account sidebar (AG-U5 P1).
 *
 * Scoped to the link list rather than the whole layout, for the same reason
 * `business/console-nav-links.tsx` is: `account/layout.tsx` stays a Server
 * Component (it reads the session with `auth.getServerUser()`; tokens never
 * touch client JS, D10 non-negotiable), and Server Components cannot read the
 * pathname.
 *
 * The shapes come from @agri/ui's console catalog — `ConsoleNavList`,
 * `ConsoleNavItem`, `consoleNavLinkClass` — so /account and /business look
 * like one system rather than two dashboards that drift apart. What this file
 * adds on top is the two things A5's sidebar has and the business console does
 * not: an icon column, and a "Settings" divider partway down.
 *
 * The profile entry renders a plain `<a>`, not a `<Link>`: it leaves for
 * id.agri.in, and prefetching another origin's route is meaningless.
 */

import { ConsoleNavItem, ConsoleNavList, consoleNavLinkClass } from "@agri/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";

export interface AccountNavEntry {
  id: string;
  href: string;
  icon: string;
  title: string;
  group?: "settings";
  external?: true;
}

export function AccountNavLinks({
  entries,
  settingsLabel,
}: {
  entries: AccountNavEntry[];
  settingsLabel: string;
}) {
  const pathname = usePathname();
  const main = entries.filter((entry) => entry.group !== "settings");
  const settings = entries.filter((entry) => entry.group === "settings");

  return (
    <>
      <NavGroup entries={main} pathname={pathname} />
      {settings.length > 0 && (
        <>
          {/* Hidden below `sm:`, where the nav collapses to a single scrolling
              pill row and a divider inside it would read as a dead pill. */}
          <p className="mt-4 hidden font-display text-[11px] font-extrabold uppercase tracking-wide text-muted sm:mb-1.5 sm:block">
            {settingsLabel}
          </p>
          <NavGroup entries={settings} pathname={pathname} />
        </>
      )}
    </>
  );
}

function NavGroup({ entries, pathname }: { entries: AccountNavEntry[]; pathname: string }) {
  return (
    <ConsoleNavList>
      {entries.map((entry) => {
        // An external entry is never "current" — you are not on id.agri.in.
        const active = !entry.external && pathname === entry.href;
        const content = (
          <>
            <span aria-hidden="true" className="mr-2 text-[15px]">
              {entry.icon}
            </span>
            {entry.title}
          </>
        );
        return (
          <ConsoleNavItem key={entry.id}>
            {entry.external ? (
              <a href={entry.href} className={consoleNavLinkClass(false)}>
                {content}
              </a>
            ) : (
              <Link
                href={entry.href}
                aria-current={active ? "page" : undefined}
                className={consoleNavLinkClass(active)}
              >
                {content}
              </Link>
            )}
          </ConsoleNavItem>
        );
      })}
    </ConsoleNavList>
  );
}
