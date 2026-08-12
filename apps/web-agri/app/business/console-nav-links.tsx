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

import { ConsoleNavItem, ConsoleNavList, consoleNavLinkClass } from "@agri/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { ConsoleModule } from "@/lib/console-modules";

export function ConsoleNavLinks({ modules }: { modules: ConsoleModule[] }) {
  const pathname = usePathname();

  return (
    <ConsoleNavList>
      {modules.map((entry) => {
        const active = pathname === entry.href;
        return (
          <ConsoleNavItem key={entry.id}>
            <Link
              href={entry.href}
              aria-current={active ? "page" : undefined}
              className={consoleNavLinkClass(active)}
            >
              {entry.title}
            </Link>
          </ConsoleNavItem>
        );
      })}
    </ConsoleNavList>
  );
}
