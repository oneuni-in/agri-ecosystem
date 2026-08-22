/**
 * A-U7 W4 — the advertiser's billing GSTIN, remembered on this device.
 *
 * WHY LOCAL AND NOT A PROFILE. The A3 reference's "Register to advertise"
 * page collects a legal name, business type, GSTIN, PAN, a billing contact
 * and a billing email, plus two consents. Exactly one of those has anywhere
 * to go today: `buyer_gstin`, and it is a field on the ORDER
 * (`POST /billing/ad-orders`), not a stored advertiser record — there is no
 * advertiser table, no PAN column, no consent row. So this remembers the one
 * value that is real, and the page renders none of the inputs that would
 * silently discard what someone typed.
 *
 * Consequences worth being honest about: it is per-browser, it is not a
 * consent record, and clearing site data loses it. That is acceptable for a
 * convenience that saves retyping 15 characters per campaign, and it is
 * exactly wrong for anything a regulator would ask about — which is why the
 * consent checkboxes are absent rather than stored here.
 *
 * When an advertiser-profile endpoint exists, this module is the one place
 * that changes: the register page and the wizard's pay step both read the
 * GSTIN through it.
 */

const GSTIN_KEY = "agri.advertiser.gstin";

/** GSTIN is exactly 15 characters, digits and uppercase letters — the same
 * shape the wizard's pay step validates against before it reaches the API. */
export const GSTIN_PATTERN = /^[0-9A-Z]{15}$/;

/** The remembered GSTIN, or "" when there is none or storage is unavailable
 * (private windows and blocked site data both throw on access). */
export function readGstin(): string {
  try {
    const value = window.localStorage.getItem(GSTIN_KEY) ?? "";
    return GSTIN_PATTERN.test(value) ? value : "";
  } catch {
    return "";
  }
}

/** Stores a valid GSTIN, or clears it when given an empty string. Anything
 * that fails the shape check is ignored rather than stored — a half-typed
 * GSTIN prefilled into a later checkout is worse than an empty field. */
export function writeGstin(value: string): void {
  try {
    if (value === "") {
      window.localStorage.removeItem(GSTIN_KEY);
      return;
    }
    if (GSTIN_PATTERN.test(value)) window.localStorage.setItem(GSTIN_KEY, value);
  } catch {
    // Storage unavailable — the field still works for this session.
  }
}
