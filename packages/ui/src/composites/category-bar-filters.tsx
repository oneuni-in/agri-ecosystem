"use client";

import { type ReactNode, useCallback, useSyncExternalStore } from "react";

/** §5's "filters leave the bar on mobile/tablet" boundary — must match the
 * `max-lg:` breakpoint on the span below (Tailwind `lg` = 1024px). */
const DESKTOP_QUERY = "(min-width: 1024px)";

function readDesktop(): boolean {
  return window.matchMedia(DESKTOP_QUERY).matches;
}

/**
 * The two attribute filters pinned right on desktop (§5). Below 1024px the
 * U1 rule is that they are NOT RENDERED — the reference's own comment reads
 * "filters leave the bar on mobile/tablet" — so hiding them with CSS alone
 * is not enough: a `display:none` interactive element is still a DOM node
 * (acceptance row A11, which axe cannot catch because it skips hidden nodes).
 *
 * Mechanism: the same media-query-conditional markup the repo already uses —
 * `matchMedia` deciding whether an island renders at all (`install-prompt.ts`
 * on `display-mode`) driven through `useSyncExternalStore` with a fixed SSR
 * snapshot (`low-data.tsx`). The SSR snapshot is TRUE and the `max-lg:hidden`
 * class stays, which is what keeps this island out of the CLS budget this
 * page's contract protects (see `site-footer.tsx`): on desktop the server
 * HTML already contains the filters, so hydration changes nothing; below
 * 1024px the server HTML has them `display:none` — never painted — and
 * hydration removes them from the DOM without a visual change. The viewport
 * is not knowable server-side (the home is per-request, §4a, and UA sniffing
 * is banned), so SSR-true + CSS is the no-shift resolution.
 */
export function CategoryBarFilters({ children }: { children: ReactNode }) {
  const desktop = useSyncExternalStore(
    useCallback((onStoreChange: () => void) => {
      const query = window.matchMedia(DESKTOP_QUERY);
      query.addEventListener("change", onStoreChange);
      return () => query.removeEventListener("change", onStoreChange);
    }, []),
    readDesktop,
    () => true,
  );
  if (!desktop) return null;
  return (
    <span
      data-testid="category-bar-filters"
      className="flex flex-none gap-[18px] pl-[22px] max-lg:hidden"
    >
      {children}
    </span>
  );
}
