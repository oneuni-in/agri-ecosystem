/**
 * The ONLY hex values legal outside tailwind/preset.js (check:hex scans
 * apps/ and packages/ui only). PWA surfaces need literals at build time:
 * manifest theme/background live in public/manifest.webmanifest (static
 * JSON), and generateViewport themeColor imports from here. MUST stay in
 * lockstep with the theme blocks in tailwind/preset.js.
 */
export const themeColors = {
  "theme-agri": { brand: "#2C6E35", paper: "#F7F8F3" },
  "theme-milk": { brand: "#2563A8", paper: "#F7F8F3" },
  "theme-organic": { brand: "#4A6B2A", paper: "#F7F8F3" },
};
