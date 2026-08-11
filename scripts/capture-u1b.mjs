// U1b — screenshot record for the rebuilt consumer surfaces, group by group.
// Usage: node scripts/capture-u1b.mjs [groupA|groupB|groupC]   (default: groupA)
//
// Copies verify-u1.mjs's hardened patterns verbatim rather than re-deriving
// them: serve-cap reset before every load (3/day per placement, one viewer
// hash per dev machine), domcontentloaded + a per-surface ready selector
// (networkidle never settles — the coins pill, bell and carousel all poll),
// one browser context per shot (NEXT_LOCALE bleed), the silent-SSO 204
// answer, and a rendered-DOM assertion before AND after the shot.
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const OUT = process.env.OUT_DIR ?? "docs/design-reference/u1b";
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:3000";
const PY = process.env.BACKEND_PY ?? "backend/core/.venv/Scripts/python.exe";
const WIDTHS = [360, 768, 1024, 1440];

const GROUPS = {
  groupA: [
    { key: "results", path: "/coimbatore/641001", ready: '[data-testid="scope-covered"]' },
    { key: "search", path: "/search?q=milk", ready: 'form[role="search"]' },
  ],
  // Group B/C surfaces are appended when those groups build.
  groupB: [],
  groupC: [],
};

const group = process.argv[2] ?? "groupA";
const surfaces = GROUPS[group];
if (!surfaces || surfaces.length === 0) {
  throw new Error(`capture-u1b: no surfaces defined for "${group}"`);
}

mkdirSync(OUT, { recursive: true });

function resetCaps() {
  try {
    execFileSync(PY, ["backend/core/scripts/seed_house_ads.py", "--reset-caps"], {
      stdio: "ignore",
    });
  } catch {
    console.warn("capture-u1b: could not reset serve caps — ad slots may show fallbacks");
  }
}

const browser = await chromium.launch();

async function shot(surface, locale, width, { full = false } = {}) {
  resetCaps();
  const ctx = await browser.newContext({ serviceWorkers: "block" });
  const page = await ctx.newPage();
  await page.route("**/api/auth/login*", (route) => route.fulfill({ status: 204, body: "" }));
  await page.setViewportSize({ width, height: 900 });
  const prefix = locale === "en" ? "" : `/${locale}`;
  await page.goto(`${BASE}${prefix}${surface.path}`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(surface.ready, { timeout: 20000 });
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({ content: "*{animation-play-state:paused!important}" });
  await page.waitForTimeout(400);
  const file = `${OUT}/${surface.key}-${locale}-${width}${full ? "-full" : ""}.png`;
  await page.screenshot({ path: file, fullPage: full });
  const still = await page.evaluate(() => ({
    url: location.href,
    nodes: document.querySelectorAll("[data-testid]").length,
  }));
  if (!still.url.startsWith("http") || still.nodes < 1) {
    throw new Error(`page blanked during capture: ${surface.key} ${locale} @${width}`);
  }
  console.log(file);
  await ctx.close();
}

for (const surface of surfaces) {
  for (const w of WIDTHS) {
    await shot(surface, "en", w);
  }
  for (const locale of ["ta", "hi"]) {
    await shot(surface, locale, 360);
    await shot(surface, locale, 1440);
  }
  await shot(surface, "en", 1440, { full: true });
  await shot(surface, "en", 360, { full: true });
}

await browser.close();
