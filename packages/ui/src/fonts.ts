import {
  Bricolage_Grotesque,
  Noto_Sans_Devanagari,
  Noto_Sans_Tamil,
  Public_Sans,
} from "next/font/google";

/** Display 600/800 (design-system.md §1.3). */
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

// preload: false — these are locale-specific (ta/hi); preloading put ~170KB
// of glyphs on every page's critical path and sank the Lighthouse perf gate
// (D04 non-negotiable: >=90 on 3G). display:swap still loads them on demand.
const tamil = Noto_Sans_Tamil({
  subsets: ["tamil"],
  weight: ["500", "700"],
  variable: "--font-tamil",
  display: "swap",
  preload: false,
});

const devanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["500", "700"],
  variable: "--font-devanagari",
  display: "swap",
  preload: false,
});

/**
 * Put on the <html> element of every app; the preset's base styles and
 * font-display/font-body utilities resolve against these variables.
 */
export const fontVariables = [
  display.variable,
  body.variable,
  tamil.variable,
  devanagari.variable,
].join(" ");
