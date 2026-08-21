import { describe, expect, it } from "vitest";

import { activeNavHref } from "./nav-active";

/**
 * AG-U5 P1 — which bottom-nav tab lights up.
 *
 * The bar shipped with `active` hardcoded (`Home: true` on every route), so
 * Home stayed lit while you stood on /notifications. P1 needs a real answer
 * because it adds an Account tab, and a tab that never lights up is the
 * visible half of a shell that claims to own navigation.
 */
const TABS = ["/", "/#mandi", "/#ask", "/account/notifications", "/account"];

describe("activeNavHref", () => {
  it("lights Home only on the home itself", () => {
    expect(activeNavHref("/", TABS)).toBe("/");
  });

  it("lights the Account tab on the dashboard", () => {
    expect(activeNavHref("/account", TABS)).toBe("/account");
  });

  it("prefers the longer match when two tabs both prefix the path", () => {
    // /account/notifications is under /account. Without longest-match both
    // tabs light, which tells the visitor nothing about where they are.
    expect(activeNavHref("/account/notifications", TABS)).toBe("/account/notifications");
  });

  it("keeps a nested module under its own tab", () => {
    expect(activeNavHref("/account/coins", TABS)).toBe("/account");
  });

  it("matches only on a segment boundary", () => {
    // The string-prefix bug: "/accountancy" starts with "/account" but is a
    // different route entirely, and "/" prefixes literally everything.
    expect(activeNavHref("/accountancy", TABS)).toBe(null);
    expect(activeNavHref("/mandi", TABS)).toBe(null);
  });

  it("never lights an anchor tab", () => {
    // /#mandi and /#ask scroll within the home; usePathname cannot see a
    // hash, so treating them as routes would light them on every home visit.
    expect(activeNavHref("/", TABS)).not.toBe("/#mandi");
    expect(activeNavHref("/#mandi", TABS)).toBe("/");
  });
});
