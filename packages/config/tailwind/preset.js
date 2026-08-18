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
    // A-U1 — the agri vertical layer from A1 FINAL v4
    // (docs/design-reference/agri/agri_home_desktop_v1.html :root). The
    // reference's --ag family maps onto the --brand slots exactly as milk's
    // --mk family did at U1: --ag → --brand, --ag-deep → --brand-deep,
    // --ag-soft → --brand-soft, --ag-soft-2 → --brand-soft-2.
    "--brand": "#3E7A45",
    "--brand-deep": "#2C5A33",
    "--brand-soft": "#EAF3E4",
    // Agri's designed mid-tone (see theme-milk's note): utility strip,
    // header tagline, hero body copy, footer body on brand surfaces.
    "--brand-soft-2": "#BFDCBA",
    "--accent": "#E9A61C",
    // A1 home sits on cream paper, the same move milk made at U1 §13.
    // Scoped to this theme; organic is untouched.
    "--page-bg": "var(--cream)",
    // Glass pills sit on --brand, and agri's #3E7A45 is light enough that
    // the shared white-alpha glass blends to ~3.8:1 under white 13px text
    // (axe, AG-A7 sweep). Agri's glass is ink-alpha instead: blended on
    // --brand it reads ~6.8:1 and matches A1's outline-on-brand chip look.
    // Scoped here so milk's white glass (which passes on its darker blue)
    // is untouched.
    "--glass": "rgba(29,42,32,.26)",
  },
  "theme-milk": {
    "--brand": "#2563A8",
    "--brand-deep": "#174A85",
    "--brand-soft": "#E9F1FA",
    // U1 §13: the mid-tone between --brand-soft and --brand. Exact value from
    // the approved reference (`docs/design-reference/desktop v3.html`, --mk-soft-2).
    // It carries every de-emphasised line on a brand surface: the utility
    // strip, the header tagline, hero body copy, footer body. Only milk has a
    // designed value today; agri/organic fall back to --brand-soft (see
    // `shared`) until their own surfaces are specced.
    "--brand-soft-2": "#B9D2EE",
    "--accent": "#E9A61C",
    // U1 §13 "cream page bg, then consume": milk.in's page surface is cream,
    // not the shared grey-green. Scoped to this theme so agri.in and
    // organicstore.in are untouched; one line to revert.
    "--page-bg": "var(--cream)",
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
  // Fallback for themes with no designed mid-tone yet (see theme-milk).
  // Declared here so `text-brand-soft-2` can never resolve to nothing.
  "--brand-soft-2": "var(--brand-soft)",
  "--paper": "#F7F8F3",
  "--page-bg": "#E9EBE2",
  "--card": "#FFFFFF",
  "--line": "#E2E7DA",
  // AA on white text: #1E9E4A measured 3.47:1, under the 4.5 floor. This was
  // carried as the "known call/rating WCAG conflict" (D02); the U1 home puts a
  // Call button on every vendor card, which turned a documented deviation into
  // a failing gate. #15803C is 5.02:1 and still unmistakably the call green.
  "--call": "#15803C",
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
  // 3.46:1 on white before; #A25F00 is 5.03:1. Same half of the D02 conflict —
  // rating stars now appear on every vendor card and in the reviews strip.
  "--rating": "#A25F00",
  "--ghost": "#F2F4EC",
  "--glass": "rgba(255,255,255,.16)",

  /* ── U1 §13 — the cream/trust/sponsored layer.
     Values are exact from the approved reference
     (`docs/design-reference/desktop v3.html` :root). Deliberately NEW names:
     --paper (#F7F8F3) and --line (#E2E7DA) are the existing green-grey page
     surface used by all three apps, and repointing them would restyle
     agri.in and organicstore.in as a side effect of a milk.in spec. */
  "--cream": "#FDFBF6", // cream page background (reference --paper)
  "--cream-line": "#EDE6D6", // cream hairline on cream (reference --paper-border)
  "--cream-deep": "#F4F0E6", // one step deeper: inset buttons, footer-adjacent (reference --paper-deep)
  // The golden sponsored border. Its own literal, NOT var(--accent): a paid
  // placement reads golden in every vertical, but organic's accent is #B5541C.
  "--ad-border": "#E9A61C",
  "--trust-bg": "#FEFAF0", // highlighted "we verify" trust card
  // Card sub-lines on cream. Distinct from --sub (#5A6A5D), which is the
  // `.vern` mother-tongue colour and is pinned by an AA contrast contract
  // (see the `.vern` component below) — it must not be re-pointed.
  // The reference's #8A8574 measures 3.69:1 on white and fails AA at the card
  // sub-line sizes it is used at (39 nodes flagged). #736E5F is 5.09:1 and
  // keeps the warm grey the reference intends, rather than falling back to the
  // green-grey --sub.
  "--muted": "#736E5F",
  // Ink for text on the golden --accent (money buttons, hotline chip, coins).
  // Follows the existing bg/fg pair convention (--coins-bg/--coins-fg).
  "--accent-ink": "#4A2E00",

  /* ── A-U1 — NEW shared tokens from A1 FINAL v4 (enter-before-use rule).
     --up/--down carry mandi price movement everywhere a change renders
     (ticker, today strip, mandi cards, sparkline strokes); --down doubles as
     the deadline-heading red-brown. On white: --up 5.40:1, --down 4.95:1 —
     both clear the 4.5 AA floor at the 11px sizes they are used at.
     --monsoon is the weather accent (5.57:1 on white).
     The severe-weather strip trio is named --severe-*, NOT the reference's
     --alert-bg/--alert-border/--alert-ink: --alert-bg/--alert-line already
     exist as the generic notice style used across milk.in forms and both
     consoles, and repointing them would restyle those surfaces from an agri
     spec. --severe-ink on --severe-bg is 6.71:1. */
  "--up": "#1E7A34",
  "--down": "#B5541C",
  "--monsoon": "#4A6B8A",
  "--severe-bg": "#FDF1E3",
  "--severe-border": "#E8B268",
  "--severe-ink": "#7A4A0D",
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

/**
 * The two raw token values a PWA manifest needs.
 *
 * A manifest is JSON consumed by the browser's install UI, so it cannot use
 * `var(--brand)` — it needs the literal. Exporting them HERE means the
 * installed app's chrome is derived from the same source as the site's, and
 * `check:hex` stays satisfied without an allowlist entry: apps/web-agri's
 * manifest imports these rather than copying them, so a token change moves
 * both together instead of leaving the installed app a stale colour.
 */
export const manifestColors = {
  background: shared["--cream"],
  theme: themes["theme-agri"]["--brand"],
};

export const agriPreset = {
  content: [],
  theme: {
    extend: {
      colors: {
        brand: "var(--brand)",
        "brand-deep": "var(--brand-deep)",
        "brand-soft": "var(--brand-soft)",
        "brand-soft-2": "var(--brand-soft-2)",
        accent: "var(--accent)",
        "accent-ink": "var(--accent-ink)",
        ink: "var(--ink)",
        sub: "var(--sub)",
        muted: "var(--muted)",
        paper: "var(--paper)",
        cream: "var(--cream)",
        "cream-line": "var(--cream-line)",
        "cream-deep": "var(--cream-deep)",
        "ad-border": "var(--ad-border)",
        "trust-bg": "var(--trust-bg)",
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
        up: "var(--up)",
        down: "var(--down)",
        monsoon: "var(--monsoon)",
        "severe-bg": "var(--severe-bg)",
        "severe-border": "var(--severe-border)",
        "severe-ink": "var(--severe-ink)",
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
      keyframes: {
        // U1 §5b — the price ticker's lane. The lane is rendered twice and
        // translated by half the track width, so the loop is seamless. Lives
        // in the preset, not one app's globals.css, because the `Marquee`
        // composite that uses it ships from @agri/ui — a keyframe defined in
        // web-milk would leave the same component motionless in the kitchen
        // sink, which is the demo-and-product-disagree failure U1 warns about.
        ticker: { from: { transform: "translateX(0)" }, to: { transform: "translateX(-50%)" } },
        // A-U1 — the A1 attraction layer. Every user of these keyframes
        // carries a motion-reduce override at the call site whose static
        // state keeps the content fully visible (A1 FINAL v4 rule): tiles
        // land at opacity 1, sparklines render fully drawn.
        pop: {
          from: { opacity: "0", transform: "translateY(12px) scale(.95)" },
          to: { opacity: "1", transform: "none" },
        },
        glow: {
          "0%, 100%": { boxShadow: "0 0 0 rgba(233,166,28,0)" },
          "50%": { boxShadow: "0 4px 22px rgba(233,166,28,.28)" },
        },
        draw: { from: { strokeDashoffset: "120" }, to: { strokeDashoffset: "0" } },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
        pulse2: {
          from: { transform: "scale(.5)", opacity: ".7" },
          to: { transform: "scale(1.4)", opacity: "0" },
        },
        // A-U4 W0 — the A1 reference's skeleton sweep (agri_home_desktop_v1
        // .html `.skeleton`/`@keyframes shimmer`). Streaming put real
        // placeholders on the home for the first time, so the reference's
        // treatment stops being decoration and becomes the thing a visitor
        // actually looks at while a section arrives.
        shimmer: {
          from: { backgroundPosition: "200% 0" },
          to: { backgroundPosition: "-200% 0" },
        },
      },
      animation: {
        // Reduced motion is honoured at the call site with
        // `motion-reduce:[animation:none]`, which degrades to a static row.
        ticker: "ticker 28s linear infinite",
        // A-U1 timings, exact from the reference.
        pop: "pop .45s cubic-bezier(.2,.7,.3,1.1) both",
        glow: "glow 3.5s ease-in-out infinite",
        draw: "draw 1.1s .25s ease-out forwards",
        float: "float 4.5s ease-in-out infinite",
        pulse2: "pulse2 1.8s ease-out infinite",
        // 1.4s, exactly the reference's timing.
        shimmer: "shimmer 1.4s infinite",
      },
      backgroundImage: {
        // A1 draws the sweep with #F1EDE2 -> #FAF7EF -> #F1EDE2; those two
        // literals ARE --cream-deep and --cream, so the tokens carry it and
        // the no-raw-hex rule holds.
        "shimmer-gradient":
          "linear-gradient(90deg, var(--cream-deep) 25%, var(--cream) 50%, var(--cream-deep) 75%)",
        "header-gradient": "linear-gradient(160deg, var(--brand-deep), var(--brand))",
        "cta-gradient": "linear-gradient(140deg, var(--brand-deep), var(--brand))",
        "eco-milk": "linear-gradient(140deg, #174A85, #2563A8)",
        "eco-organic": "linear-gradient(140deg, #35511C, #4A6B2A)",
        "eco-coins": "linear-gradient(140deg, #8A5B00, #C98A10)",
        "gold-gradient": "linear-gradient(140deg, #8A5B00, #B5541C)",
        // A-U1 recipes from A1 FINAL v4. band-gradient is the search band and
        // the Today strip's "ask" card (135deg, brand into a brand/deep mix);
        // earn/tip are the warm gold card washes of the coins family. Exact
        // reference stops — recipes live here so app code stays hex-free.
        "band-gradient":
          "linear-gradient(135deg, var(--brand) 0%, color-mix(in srgb, var(--brand) 55%, var(--brand-deep)) 100%)",
        "earn-gradient": "linear-gradient(135deg, #FEF9EE, #FDF3DC)",
        "tip-gradient": "linear-gradient(120deg, #FEFAF0, #FBF3DE)",
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
          // No opacity. `.vern` is the mother-tongue line (UX law 1), almost
          // always --sub on --card: that is 5.74:1 on its own, but blending it
          // to 85% dropped it to 4.14:1 - under the 4.5:1 AA floor, and at
          // .78em it is small text that gets no large-text exemption. axe
          // flagged 19 instances across home/pincode/post-need (D29). The
          // vernacular line was the least readable text on the page for the
          // readers who most need it; full opacity fixes that.
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
