"use client";

/**
 * M5 Task 16 fix (coordinator review): pathname-aware active state for the
 * console nav. Scoped to just the <ul>/links, not the whole layout -
 * business/layout.tsx must stay a Server Component (it calls
 * auth.getAccessToken() to probe billing_enabled/ads_enabled server-side;
 * tokens never touch client JS, D10 non-negotiable), and Server Components
 * have no built-in access to the current pathname. This is the ONE <nav>'s
 * link list, still - layout.tsx renders the `<nav>` wrapper and the
 * "Business console" heading; this component owns only the <ul> so the
 * same module list can know which entry is current. The registry contract
 * (lib/console-modules.ts) and layout.tsx's auth behavior are untouched.
 *
 * Same responsive classes apply to both the below-`sm:` pill row and the
 * `sm:`+ sidebar - only the active/inactive fill differs, mirroring
 * campaign-wizard.tsx's own step-pill convention (current = bg-ink/text-card,
 * other = bg-line/text-ink) for the pill row, and the RadioCard "selected"
 * convention (bg-brand-soft/text-brand-deep) for the sidebar row.
 */

import { cn } from "@agri/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { ConsoleModule } from "@/lib/console-modules";

export function ConsoleNavLinks({ modules }: { modules: ConsoleModule[] }) {
  const pathname = usePathname();

  return (
    <ul className="flex gap-2 sm:block sm:space-y-1">
      {modules.map((entry) => {
        const active = pathname === entry.href;
        return (
          <li key={entry.id} className="flex-none">
            <Link
              href={entry.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-[44px] items-center whitespace-nowrap rounded-pill px-4 text-[13px] font-semibold sm:block sm:min-h-0 sm:whitespace-normal sm:rounded-card sm:px-3 sm:py-2 sm:text-[14px]",
                active
                  ? "bg-ink text-card sm:bg-brand-soft sm:text-brand-deep"
                  : "bg-line text-ink sm:bg-transparent sm:font-normal sm:text-ink sm:hover:bg-line",
              )}
            >
              {entry.title}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
