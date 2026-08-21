/**
 * The supported languages, written in their own scripts.
 *
 * These are autonyms, not copy: "தமிழ்" is தமிழ் in an English page and in a
 * Hindi one, so they are a constant rather than three catalogue entries — the
 * design-system rule the header switcher already states ("language glyphs are
 * written in their own script, never translated").
 *
 * It lives in lib/ rather than beside the card because it is data, not
 * markup. Note the two locale switchers (`app/locale-switcher.tsx`,
 * `app/business/locale-switcher.tsx`) still carry their own copies of these
 * names: pointing them here is a real tidy but it would pull the public
 * header and the business console into AG-U5's diff, and neither is in this
 * pass's proof loop. Recorded as a follow-up in docs/qa/ag-u5-drift.md
 * rather than done half-way.
 */

export interface Language {
  code: string;
  /** Compact form for a switcher control. */
  glyph: string;
  /** The language's name in its own script. */
  name: string;
}

export const LANGUAGES: readonly Language[] = [
  { code: "en", glyph: "EN", name: "English" },
  { code: "ta", glyph: "த", name: "தமிழ்" },
  { code: "hi", glyph: "हि", name: "हिंदी" },
] as const;

/**
 * The name to print for a stored language code.
 *
 * An unknown code prints as itself. A profile can carry a value this build
 * has no autonym for — showing the code says "ta" honestly, where defaulting
 * to English would state something false about the person's setting.
 */
export function languageName(code: string | null): string | null {
  if (code === null) return null;
  return LANGUAGES.find((entry) => entry.code === code)?.name ?? code;
}
