"use client";

/**
 * The shell nav's client half: receives the ROLE-FILTERED item list from the
 * server (`AdminChrome` filters against the session; this component never
 * sees roles) and adds the one thing only the client knows — which route is
 * active, marked with `aria-current="page"`.
 */
import { ConsoleNavItem, ConsoleNavList, consoleNavLinkClass } from "@agri/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { AdminNavItem } from "./nav-items";

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AdminNav({ items }: { items: readonly AdminNavItem[] }) {
  const pathname = usePathname();
  return (
    <ConsoleNavList>
      {items.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <ConsoleNavItem key={item.href}>
            <Link
              href={item.href}
              className={consoleNavLinkClass(active)}
              {...(active ? { "aria-current": "page" as const } : {})}
            >
              {item.title}
            </Link>
          </ConsoleNavItem>
        );
      })}
    </ConsoleNavList>
  );
}
