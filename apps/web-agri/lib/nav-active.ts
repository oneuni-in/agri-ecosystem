/**
 * Which navigation target the current path is "in" (AG-U5 P1).
 *
 * Longest match wins, so /account/notifications lights the Notifications tab
 * rather than lighting both it and the Account tab it nests under.
 *
 * Two rules that a plain `startsWith` gets wrong, and which the tests pin:
 *  - The match must land on a SEGMENT boundary. "/accountancy" begins with
 *    "/account" and has nothing to do with it.
 *  - "/" is exact-only. As a prefix it matches every route on the site.
 *
 * Anchor targets ("/#mandi") are skipped entirely: they scroll within a page,
 * `usePathname` cannot see a hash, and treating them as routes would light
 * them on every visit to the page they live on.
 */
export function activeNavHref(pathname: string, hrefs: readonly string[]): string | null {
  const path = pathname.split("#")[0] || "/";
  let best: string | null = null;
  for (const href of hrefs) {
    if (href.includes("#")) continue;
    const matches = href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
    if (matches && (best === null || href.length > best.length)) best = href;
  }
  return best;
}
