import { Bricolage_Grotesque, Public_Sans } from "next/font/google";

/**
 * A-U1 AG-A8 — the latin-only sibling of fonts.ts, in its OWN module on
 * purpose: next/font emits @font-face rules into the CSS of every app that
 * imports the module, even for variables that are never applied — and a
 * `--font-tamil: "Noto Sans Tamil"` override then resolves straight back to
 * those rules and re-downloads the font. An app that wants SYSTEM Indic
 * fonts must never import fonts.ts at all.
 *
 * Why agri wants that: the A1 design puts Tamil and Hindi inside the
 * largest headings of a 3G-first surface. The on-demand Indic webfonts
 * (~170 KB) sat inside Lighthouse's lantern LCP graph (deterministic
 * ~3.9 s render delay, three CI runs within 30 ms) and are real bytes on
 * every cold cache. Android/ChromeOS ship the exact same Noto faces;
 * other platforms pick their own Indic face per glyph.
 *
 * Apps using this variant MUST define --font-tamil/--font-devanagari in
 * their own CSS (see web-agri globals.css) — an undefined var() poisons
 * the whole font-family declaration. Milk keeps fonts.ts and is untouched.
 */
const display = Bricolage_Grotesque({
  subsets: ["latin"],
  weight: ["600", "800"],
  variable: "--font-display",
  display: "swap",
});

const body = Public_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-body",
  display: "swap",
});

/** Put on the <html> element; Indic vars come from the app's own CSS. */
export const fontVariablesSystemIndic = [display.variable, body.variable].join(" ");
