/**
 * The ONLY hex values legal outside tailwind/preset.js (check:hex scans
 * apps/ and packages/ui only). PWA surfaces need literals at build time:
 * manifest theme/background live in public/manifest.webmanifest (static
 * JSON), and generateViewport themeColor imports from here. MUST stay in
 * lockstep with the theme blocks in tailwind/preset.js.
 */
export const themeColors = {
  // A-U1: agri brand re-entered from A1 FINAL v4 (--ag). paper stays the
  // shared --paper, matching how milk kept it when its page went cream.
  "theme-agri": { brand: "#3E7A45", paper: "#F7F8F3" },
  "theme-milk": { brand: "#2563A8", paper: "#F7F8F3" },
  "theme-organic": { brand: "#4A6B2A", paper: "#F7F8F3" },
};
