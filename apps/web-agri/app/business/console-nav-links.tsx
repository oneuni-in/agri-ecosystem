"use client";

/**
 * Pathname-aware active state for the console nav (M5 Task 16, rebuilt on
 * the U2 catalog). Scoped to just the link list, not the whole layout —
 * business/layout.tsx must stay a Server Component (it probes ownership and
 * billing/ads gates with auth.getAccessToken(); tokens never touch client
 * JS, D10 non-negotiable), and Server Components can't read the pathname.
 *
 * The shapes live in @agri/ui's console catalog (`ConsoleNavList` /
 * `ConsoleNavItem` / `consoleNavLinkClass`) so the kitchen sink renders the
 * SAME code — this file only binds them to Next's Link + usePathname.
 */

import {
  ConsoleNavIcon,
  ConsoleNavItem,
  ConsoleNavList,
  consoleNavLinkClass,
} from "@agri/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { ConsoleModule } from "@/lib/console-modules";

export function ConsoleNavLinks({ modules }: { modules: ConsoleModule[] }) {
  const pathname = usePathname();

  return (
    // A-U7: `lg` — the business rail is 218px wide and only earns the space
    // from `lg:` up; below that it is the same scrollable pill row.
    <ConsoleNavList breakpoint="lg">
      {modules.map((entry) => {
        const active = pathname === entry.href;
        return (
          <ConsoleNavItem key={entry.id} breakpoint="lg">
            <Link
              href={entry.href}
              aria-current={active ? "page" : undefined}
              className={consoleNavLinkClass(active, "lg")}
            >
              <ConsoleNavIcon>{entry.icon}</ConsoleNavIcon>
              {entry.title}
            </Link>
          </ConsoleNavItem>
        );
      })}
    </ConsoleNavList>
  );
}
