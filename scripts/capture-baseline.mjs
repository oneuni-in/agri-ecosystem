// Captures the D02 visual-regression baseline: one full-page screenshot of
// the demo route per theme. Run with the web-agri server up on :3002.
// Future PRs touching packages/ui compare against these (design-system.md §4).
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const OUT_DIR = "docs/design-reference/baseline";
const THEMES = ["agri", "milk", "organic"];
const BASE = process.env.DEMO_URL ?? "http://localhost:3002/demo";

mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

for (const theme of THEMES) {
  await page.goto(`${BASE}?theme=${theme}`, { waitUntil: "networkidle" });
  // Fonts are render-blocking for layout fidelity — wait until loaded.
  await page.evaluate(() => document.fonts.ready);
  // Full-page capture stamps sticky elements at the first viewport's edge,
  // overlapping content mid-page. Pin them to their natural position; the
  // nav/switcher still render at the document ends.
  await page.addStyleTag({ content: ".sticky { position: static !important; }" });
  await page.screenshot({ path: `${OUT_DIR}/demo-${theme}.png`, fullPage: true });
  console.log(`captured ${OUT_DIR}/demo-${theme}.png`);
}

await browser.close();
