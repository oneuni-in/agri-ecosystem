"use client";

/**
 * Wordmark link for the site header (A-U4b O5, AG-A64). `HeaderStack` is
 * routing-free by contract, so the app supplies the link node via the `logo`
 * slot. Locale routing follows this app's existing idiom: `Link` /
 * `usePathname` from `@/i18n/navigation` (next-intl), exactly as
 * `locale-switcher.tsx` does — `href="/"` becomes the locale-prefixed home
 * and `usePathname()` excludes the locale prefix, so the home check is a
 * plain `=== "/"` at every locale.
 *
 * Home-page rule: on the home page the wordmark must NOT be a link to where
 * you already are — it renders as plain text there. The header lives in
 * `[locale]/layout.tsx` (Server Component, no pathname access), so the check
 * is this small pathname-aware client segment. No `useSearchParams` here, so
 * unlike LocaleSwitcher it needs no Suspense boundary and does not opt the
 * page out of static rendering.
 *
 * Zero CLS: `usePathname` resolves during SSR, so server and client render
 * the same node — no hydration swap. `.tap-target` reaches the 44px floor
 * via an ::after hit box without changing the rendered box; underline and
 * colour are inherited from the wordmark span in HeaderStack. The link's
 * accessible name is the wordmark text itself.
 */

import type { ReactNode } from "react";

import { Link, usePathname } from "@/i18n/navigation";

export function BrandLink({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/") return <>{children}</>;
  return (
    <Link href="/" className="tap-target text-inherit no-underline">
      {children}
    </Link>
  );
}
