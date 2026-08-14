/**
 * U4 A21 regression (unit half): §10a's dismissal must persist via the same
 * cookie mechanism as §10b's — these helpers ARE that mechanism, so pin the
 * exact strings both surfaces read and write. The browser half (dismiss →
 * reload → still gone) runs in e2e/pwa.spec.ts and, for real Chrome,
 * e2e/push-verification.spec.ts.
 */
import { describe, expect, it } from "vitest";

import {
  DISMISS_MAX_AGE,
  INSTALL_DISMISS_COOKIE,
  PRICE_ALERT_DISMISS_COOKIE,
  dismissalCookie,
  isDismissedIn,
} from "./dismissal";

describe("dismissalCookie", () => {
  it("writes a 30-day, path-wide, lax cookie — never localStorage", () => {
    expect(DISMISS_MAX_AGE).toBe(60 * 60 * 24 * 30);
    expect(dismissalCookie(PRICE_ALERT_DISMISS_COOKIE)).toBe(
      `milk_price_alert=0; path=/; max-age=${DISMISS_MAX_AGE}; samesite=lax`,
    );
  });

  it("round-trips through a document.cookie-shaped header", () => {
    const written = dismissalCookie(PRICE_ALERT_DISMISS_COOKIE).split(";")[0]!;
    expect(isDismissedIn(written, PRICE_ALERT_DISMISS_COOKIE)).toBe(true);
    expect(isDismissedIn(`NEXT_LOCALE=en; ${written}; agri_loc=641001`, PRICE_ALERT_DISMISS_COOKIE)).toBe(
      true,
    );
  });
});

describe("isDismissedIn", () => {
  it("the two surfaces stay independent: dismissing one never silences the other", () => {
    const installDismissed = dismissalCookie(INSTALL_DISMISS_COOKIE).split(";")[0]!;
    expect(isDismissedIn(installDismissed, INSTALL_DISMISS_COOKIE)).toBe(true);
    expect(isDismissedIn(installDismissed, PRICE_ALERT_DISMISS_COOKIE)).toBe(false);
    const alertDismissed = dismissalCookie(PRICE_ALERT_DISMISS_COOKIE).split(";")[0]!;
    expect(isDismissedIn(alertDismissed, INSTALL_DISMISS_COOKIE)).toBe(false);
  });

  it("does not match absence or lookalike values", () => {
    expect(isDismissedIn("", PRICE_ALERT_DISMISS_COOKIE)).toBe(false);
    expect(isDismissedIn("milk_price_alert=1", PRICE_ALERT_DISMISS_COOKIE)).toBe(false);
    expect(isDismissedIn("milk_price_alert_x=0", PRICE_ALERT_DISMISS_COOKIE)).toBe(false);
  });
});
