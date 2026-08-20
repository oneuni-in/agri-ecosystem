"use client";

/**
 * Wordmark link for the site header (A-U4b O5, AG-A64). `HeaderStack` is
 * routing-free by contract, so the app supplies the link node via the `logo`
 * slot; this wrapper is the ONE place that binds it to Next's Link.
 *
 * Home-page rule: on `/` the wordmark must NOT be a link to where you
 * already are (same rule the §21 family strip applies to the agri tile,
 * page.tsx "you are here, not a link"). The header renders in the root
 * layout — a Server Component with no pathname access — so the check lives
 * here as a pathname-aware client segment, the same scoping precedent as
 * `console-nav-links.tsx` (client island for just the pathname-dependent
 * bit, layout stays a Server Component).
 *
 * Zero CLS (AG-A8): `usePathname` resolves during SSR too, so server and
 * client render the same node — no hydration swap. `.tap-target` reaches
 * the 44px floor via an ::after hit box without changing the rendered box;
 * underline and colour are inherited from the wordmark span in HeaderStack.
 * The link's accessible name is the wordmark text itself.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

export function BrandLink({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/") return <>{children}</>;
  return (
    <Link href="/" className="tap-target text-inherit no-underline">
      {children}
    </Link>
  );
}
