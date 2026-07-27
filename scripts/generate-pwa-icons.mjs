// One-off generator: renders the Milk.in glyph SVG to the committed PWA
// PNGs. Re-run only when the brand mark changes:
//   node scripts/generate-pwa-icons.mjs
// Hex here mirrors packages/config/theme-colors.js (root scripts/ is outside
// check:hex's scan set - apps/ and packages/ui only).
import { mkdirSync } from "node:fs";

import sharp from "sharp";

const BRAND = "#2563A8";
const PAPER = "#F7F8F3";

// Simple milk-bottle glyph, centered; `flat` fills the full square (maskable
// safe-zone) while the default gets the rounded-card corner radius.
const svg = (flat) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="${flat ? 0 : 96}" fill="${BRAND}"/>
  <g transform="translate(256 276)">
    <path d="M-62 -138 h124 v36 l22 44 v168 a24 24 0 0 1 -24 24 h-120 a24 24 0 0 1 -24 -24 v-168 l22 -44 z"
      fill="${PAPER}"/>
    <path d="M-84 -14 q42 -26 84 0 t84 0 v128 a24 24 0 0 1 -24 24 h-120 a24 24 0 0 1 -24 -24 z"
      fill="${BRAND}" opacity="0.25"/>
  </g>
</svg>`;

const out = "apps/web-milk/public/icons";
mkdirSync(out, { recursive: true });
await sharp(Buffer.from(svg(false))).resize(192, 192).png().toFile(`${out}/icon-192.png`);
await sharp(Buffer.from(svg(false))).resize(512, 512).png().toFile(`${out}/icon-512.png`);
await sharp(Buffer.from(svg(true))).resize(512, 512).png().toFile(`${out}/maskable-512.png`);
await sharp(Buffer.from(svg(true))).resize(180, 180).png().toFile(`${out}/apple-touch-icon.png`);
console.log("icons written to", out);
