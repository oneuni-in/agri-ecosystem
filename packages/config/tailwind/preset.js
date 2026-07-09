/**
 * @agri/config — Tailwind preset. THE only place hex colors are allowed
 * (CLAUDE.md: tokens only — no raw hex in app code).
 *
 * Values are exact from docs/design-system.md §1; the mockup at
 * docs/design-reference/preview_frontend.html is the visual source of truth.
 *
 * @type {import("tailwindcss").Config}
 */
import plugin from "tailwindcss/plugin";

/** §1.1 per-site themes, switched via data-theme on each app's root element. */
const themes = {
  "theme-agri": {
    "--brand": "#2C6E35",
    "--brand-deep": "#1E4E26",
    "--brand-soft": "#E8F2E6",
    "--accent": "#E9A61C",
  },
  "theme-milk": {
    "--brand": "#2563A8",
    "--brand-deep": "#174A85",
    "--brand-soft": "#E9F1FA",
    "--accent": "#E9A61C",
  },
  "theme-organic": {
    "--brand": "#4A6B2A",
    "--brand-deep": "#35511C",
    "--brand-soft": "#EFF3E4",
    "--accent": "#B5541C",
  },
};

/** §1.2 shared neutrals & semantics (+ exact recipe colors from the mockup). */
const shared = {
  "--ink": "#1D2A20",
  "--sub": "#5A6A5D",
  "--paper": "#F7F8F3",
  "--page-bg": "#E9EBE2",
  "--card": "#FFFFFF",
  "--line": "#E2E7DA",
  "--call": "#1E9E4A",
  "--wa": "#22B45A",
  "--wa-soft": "#E6F8EC",
  "--wa-deep": "#157A3C",
  "--wa-line": "#BDE8CC",
  "--coins-bg": "#FFF3D6",
  "--coins-fg": "#8A5B00",
  "--alert-bg": "#FFF6E4",
  "--alert-line": "#F0DCA8",
  "--helpband": "#153A1D",
  "--verified-bg": "#E1F3E5",
  "--verified-fg": "#156A2E",
  "--sponsored-bg": "#FFF1D2",
  "--sponsored-fg": "#8A5B00",
  "--cert-bg": "#EAF2DC",
  "--cert-fg": "#3E5A14",
  "--rating": "#C77700",
  "--ghost": "#F2F4EC",
  "--glass": "rgba(255,255,255,.16)",
};

/** Pastel icon-square tints used by CategoryTile / ListingCard / ProductCard. */
const tint = {
  green: "#E8F2E6",
  sand: "#F4EEDB",
  blush: "#FBEAE2",
  peach: "#FDEFD8",
  bluegray: "#EAF0F7",
  aqua: "#E4F3F1",
  cream: "#FDF3D9",
  lilac: "#EDEBF8",
  gold: "#FFF1D2",
  violet: "#F0EAF6",
  stone: "#EFEADF",
  mist: "#F2F4EC",
  sky: "#E4F0F7",
  blue: "#E9F1FA",
  leaf: "#EAF2DC",
  sage: "#EFF3E4",
  fern: "#EFF6EA",
};

export const agriPreset = {
  content: [],
  theme: {
    extend: {
      colors: {
        brand: "var(--brand)",
        "brand-deep": "var(--brand-deep)",
        "brand-soft": "var(--brand-soft)",
        accent: "var(--accent)",
        ink: "var(--ink)",
        sub: "var(--sub)",
        paper: "var(--paper)",
        page: "var(--page-bg)",
        card: "var(--card)",
        line: "var(--line)",
        call: "var(--call)",
        wa: "var(--wa)",
        "wa-soft": "var(--wa-soft)",
        "wa-deep": "var(--wa-deep)",
        "wa-line": "var(--wa-line)",
        "coins-bg": "var(--coins-bg)",
        "coins-fg": "var(--coins-fg)",
        "alert-bg": "var(--alert-bg)",
        "alert-line": "var(--alert-line)",
        helpband: "var(--helpband)",
        "verified-bg": "var(--verified-bg)",
        "verified-fg": "var(--verified-fg)",
        "sponsored-bg": "var(--sponsored-bg)",
        "sponsored-fg": "var(--sponsored-fg)",
        "cert-bg": "var(--cert-bg)",
        "cert-fg": "var(--cert-fg)",
        rating: "var(--rating)",
        ghost: "var(--ghost)",
        glass: "var(--glass)",
        "certgold-bg": "#FFFBEE",
        "certgold-line": "#CBB77A",
        tint,
      },
      borderRadius: {
        card: "16px",
        btn: "12px",
        pill: "99px",
        band: "18px",
        icon: "14px",
      },
      fontFamily: {
        display: ["var(--font-display)", "var(--font-body)", "system-ui", "sans-serif"],
        body: [
          "var(--font-body)",
          "var(--font-tamil)",
          "var(--font-devanagari)",
          "system-ui",
          "sans-serif",
        ],
      },
      boxShadow: {
        lift: "0 6px 16px rgba(0,0,0,.08)",
        search: "0 4px 18px rgba(0,0,0,.12)",
        pin: "0 6px 20px rgba(0,0,0,.18)",
        callglow: "0 4px 14px rgba(30,158,74,.4)",
        nav: "0 -6px 20px rgba(0,0,0,.06)",
        ai: "0 4px 12px color-mix(in srgb, var(--brand) 40%, transparent)",
      },
      backgroundImage: {
        "header-gradient": "linear-gradient(160deg, var(--brand-deep), var(--brand))",
        "cta-gradient": "linear-gradient(140deg, var(--brand-deep), var(--brand))",
        "eco-milk": "linear-gradient(140deg, #174A85, #2563A8)",
        "eco-organic": "linear-gradient(140deg, #35511C, #4A6B2A)",
        "eco-coins": "linear-gradient(140deg, #8A5B00, #C98A10)",
        "gold-gradient": "linear-gradient(140deg, #8A5B00, #B5541C)",
      },
    },
  },
  plugins: [
    plugin(({ addBase, addComponents, addUtilities }) => {
      addBase({
        ":root": { ...shared, ...themes["theme-agri"] },
        '[data-theme="theme-agri"]': themes["theme-agri"],
        '[data-theme="theme-milk"]': themes["theme-milk"],
        '[data-theme="theme-organic"]': themes["theme-organic"],
        body: {
          backgroundColor: "var(--page-bg)",
          color: "var(--ink)",
          fontFamily:
            "var(--font-body), var(--font-tamil), var(--font-devanagari), system-ui, sans-serif",
          fontSize: "15px",
          lineHeight: "1.5",
          "-webkit-font-smoothing": "antialiased",
        },
        // §1.4 — 3px accent ring, offset 2. Never remove.
        ":focus-visible": {
          outline: "3px solid var(--accent)",
          outlineOffset: "2px",
          borderRadius: "6px",
        },
      });
      addComponents({
        // §1.3 — under EVERY category label and key CTA, own line.
        ".vern": {
          display: "block",
          fontSize: ".78em",
          fontWeight: "500",
          opacity: ".85",
          lineHeight: "1.3",
        },
      });
      addUtilities({
        // Expands the hit area of visually-small pills to the 44px minimum
        // (§1.5) without changing their rendered size.
        ".tap-target": { position: "relative" },
        ".tap-target::after": {
          content: '""',
          position: "absolute",
          left: "50%",
          top: "50%",
          transform: "translate(-50%, -50%)",
          width: "max(100%, 44px)",
          height: "max(100%, 44px)",
        },
      });
    }),
  ],
};

export default agriPreset;
