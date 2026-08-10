// U1 Pass 1 — side-by-side capture: the real home at the four NN1 viewports,
// plus the approved reference at the same widths, plus TA/HI (NN3).
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

// Every page load burns one of the 3/day-per-placement serve caps (a fraud
// control, and every request from this machine shares one viewer hash), so a
// multi-viewport sweep would capture the house fallback instead of a served
// creative from the 4th shot on. Same escape hatch e2e uses.
const PY = process.env.BACKEND_PY ?? "backend/core/.venv/Scripts/python.exe";
function resetCaps() {
  try {
    execFileSync(PY, ["backend/core/scripts/seed_house_ads.py", "--reset-caps"], {
      stdio: "ignore",
    });
  } catch {
    console.warn("capture-u1: could not reset serve caps — ad slots may show fallbacks");
  }
}

const OUT = process.env.OUT_DIR ?? "docs/design-reference/u1";
const BASE = process.env.BASE_URL ?? "http://localhost:3010";
const REF = "file:///D:/agri-ecosystem/docs/design-reference/desktop%20v3.html";
const WIDTHS = [360, 768, 1024, 1440];
const TAG = process.env.TAG ?? "after";

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();

async function shot(url, path, width, { full = false } = {}) {
  if (url.startsWith(BASE)) resetCaps();
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  // The hero carousel autoplays; freeze animation so repeat runs are stable.
  await page.addStyleTag({ content: "*{animation-play-state:paused!important}" });
  await page.waitForTimeout(400);
  await page.screenshot({ path, fullPage: full });
  console.log(path);
  await page.close();
}

for (const w of WIDTHS) {
  await shot(`${BASE}/`, `${OUT}/home-${TAG}-${w}.png`, w);
  await shot(REF, `${OUT}/reference-${w}.png`, w);
}
// NN3: TA/HI must render without layout break on every section.
for (const loc of ["ta", "hi"]) {
  await shot(`${BASE}/${loc}`, `${OUT}/home-${TAG}-${loc}-360.png`, 360);
  await shot(`${BASE}/${loc}`, `${OUT}/home-${TAG}-${loc}-1440.png`, 1440);
}
// Full-page desktop + mobile for the record.
await shot(`${BASE}/`, `${OUT}/home-${TAG}-full-1440.png`, 1440, { full: true });
await shot(`${BASE}/`, `${OUT}/home-${TAG}-full-360.png`, 360, { full: true });

await browser.close();
