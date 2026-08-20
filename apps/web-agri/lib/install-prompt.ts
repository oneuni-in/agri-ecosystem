/**
 * A-U4b O8 (AG-A66) — §19 PWA install band: the pure decision logic.
 *
 * The band's whole contract is "no dead button ever", and this function IS
 * that contract, kept out of the component so it is unit-testable without a
 * DOM (the same split as `lib/otp.ts` and `lib/mandi.ts`):
 *
 *   isStandalone → "absent"  — already installed; offering an install is noise.
 *   hasPrompt    → "button"  — a live `beforeinstallprompt` is HELD, so the
 *                              button genuinely opens the browser dialog.
 *   isIOS        → "ios"     — Safari never fires the event; rendering a
 *                              button would be a lie, so the band carries the
 *                              Add-to-Home-Screen instruction instead (the
 *                              same honesty rule as `lib/push.ts`, whose
 *                              "denied"/"ios-install" states never render a
 *                              button that cannot work).
 *   otherwise    → "absent"  — unsupported browser, desktop with the app
 *                              already installed, etc. Nothing is rendered,
 *                              which is also why the island costs zero CLS
 *                              risk on first paint: no space is reserved.
 */

export type InstallSurface = "button" | "ios" | "absent";

export interface InstallFlags {
  /** A live, un-consumed `beforeinstallprompt` is held (Android/Chrome). */
  hasPrompt: boolean;
  /** iOS Safari family, which never fires the event. */
  isIOS: boolean;
  /** Running as an installed app (display-mode standalone / navigator.standalone). */
  isStandalone: boolean;
}

export function decideInstallSurface({ hasPrompt, isIOS, isStandalone }: InstallFlags): InstallSurface {
  if (isStandalone) return "absent";
  // A held event outranks the UA sniff: if the browser PROVED it can prompt,
  // the button works regardless of what the UA string claims.
  if (hasPrompt) return "button";
  if (isIOS) return "ios";
  return "absent";
}

/**
 * The same regex `lib/push.ts` already uses for its "ios-install" state —
 * one sniff, not two that drift. Known, accepted gap (also push.ts's):
 * iPadOS 13+ in desktop mode reports a Macintosh UA and resolves to
 * "absent" — an absent band, never a dead button.
 */
export function isIosUserAgent(userAgent: string): boolean {
  return /iPad|iPhone|iPod/.test(userAgent);
}
