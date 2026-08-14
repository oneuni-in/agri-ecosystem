/**
 * "Dismissed stays dismissed" cookie mechanics (U1 item 33 "never nag"),
 * shared by every surface that offers a dismissal. Cookie, never localStorage
 * — U1's DO-NOT list bans localStorage outright.
 *
 * Each surface owns a NAMED cookie rather than sharing one: the install
 * surfaces (§10b band + the fixed banner) are one ask and share `milk_a2hs`;
 * the §10a price-alert card is a different ask with its own lifetime, so
 * waving away "install the app" must not also silence "want price alerts?"
 * and vice versa (U4 A21).
 *
 * Pure string functions so the 30-day contract is unit-testable without a
 * DOM; callers pass `document.cookie` in and assign the returned string back.
 */

export const DISMISS_MAX_AGE = 60 * 60 * 24 * 30;

/** §10b install band + fixed banner (D28) — the name both have always used. */
export const INSTALL_DISMISS_COOKIE = "milk_a2hs";
/** §10a price-alert opt-in card (U4 A21). */
export const PRICE_ALERT_DISMISS_COOKIE = "milk_price_alert";

/** Was this surface dismissed inside its cookie's 30-day window? */
export function isDismissedIn(cookieHeader: string, name: string): boolean {
  return cookieHeader.split("; ").includes(`${name}=0`);
}

/** The `document.cookie` assignment that records a dismissal for 30 days. */
export function dismissalCookie(name: string): string {
  return `${name}=0; path=/; max-age=${DISMISS_MAX_AGE}; samesite=lax`;
}
