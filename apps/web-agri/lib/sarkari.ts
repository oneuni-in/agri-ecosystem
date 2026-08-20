/**
 * A-U4b O2 (AG-A61) — pure logic for the sarkari hub's detail dialog.
 *
 * The sarkari cards stopped being one-click exits: with JS, a plain click
 * opens a descriptive dialog and leaving agri.in is a deliberate second
 * click. These helpers are the island's decision logic, kept pure so the
 * node-env vitest suite can pin them down.
 */

/** One localized string from `data/sarkari.json` — E5 copy, per locale. */
export interface SarkariText {
  en: string;
  ta: string;
  hi: string;
}

/**
 * Picks the locale's string, falling back to English when the locale is not
 * ta/hi or the translation is missing/blank (the locale-completeness gate
 * makes blank unlikely, but data files are edited by hand).
 */
export function pickSarkariText(text: SarkariText, locale: string): string {
  const value = locale === "ta" || locale === "hi" ? text[locale] : text.en;
  return value && value.trim() !== "" ? value : text.en;
}

/** The click facts the intercept decision needs — a structural subset of
 * React.MouseEvent so tests can feed plain objects. */
export interface CardClick {
  defaultPrevented: boolean;
  button: number;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}

/**
 * True when a click on a sarkari card should open the detail dialog instead
 * of navigating. Only a plain left-click is intercepted: modified clicks
 * (ctrl/cmd/shift/alt) and non-primary buttons keep their browser meaning —
 * open-in-new-tab/window must keep working, and the no-JS path (no handler
 * at all) already navigates.
 */
export function shouldInterceptClick(event: CardClick): boolean {
  return (
    !event.defaultPrevented &&
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  );
}
