// U1 live verification in a real Chromium: per-locale screenshots, an
// untranslated-chrome probe, console errors, and the NN5 no-wrap check on the
// category bar across 320-1920px.
//
// Two traps this harness is deliberately hardened against, because both turn a
// non-result into something that reads like a pass:
//   · `waitUntil: "networkidle"` never settles (the coins pill, the bell and
//     the ad carousel all poll), so the navigation ends on chrome-error and
//     every probe returns EMPTY — i.e. "no untranslated strings".
//   · next-intl writes a NEXT_LOCALE cookie, so a "/" visit after a "/ta" one
//     redirects mid-run and destroys the execution context. Every page gets
//     its own browser context.
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const OUT = process.env.OUT_DIR ?? "docs/design-reference/u1";
// 127.0.0.1, not localhost: Chromium prefers ::1 and the dev server binds IPv4.
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:3000";
const PY = process.env.BACKEND_PY ?? "backend/core/.venv/Scripts/python.exe";
const LOCALES = [
  ["en", "/"],
  ["ta", "/ta"],
  ["hi", "/hi"],
];

mkdirSync(OUT, { recursive: true });

/** The dev serve-cap is 3/day per placement and every request from this
 * machine shares one viewer hash, so an unguarded sweep captures the house
 * fallback instead of a served creative from the 4th load on. */
function resetCaps() {
  try {
    execFileSync(PY, ["backend/core/scripts/seed_house_ads.py", "--reset-caps"], {
      stdio: "ignore",
    });
  } catch {
    console.warn("verify-u1: could not reset serve caps — ad slots may show fallbacks");
  }
}

/** Visible UI chrome only. Business names, product names, review bodies and
 * district names come from the database in English and are NOT translatable
 * strings — excluding them is what makes this probe meaningful. */
const PROBE = ({ dataSel, allowedSource }) => {
  const allowed = new RegExp(allowedSource, "i");
  const skip = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"]);
  const dataNodes = [...document.querySelectorAll(dataSel)];
  const out = [];
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    const p = n.parentElement;
    if (!p || skip.has(p.tagName)) continue;
    if (dataNodes.some((d) => d.contains(n))) continue;
    if (!p.offsetParent && p.tagName !== "BODY") continue;
    const t = n.textContent.trim();
    if (t && /[A-Za-z]{3,}/.test(t) && !allowed.test(t)) out.push(t);
  }
  return [...new Set(out)];
};

const DATA_SEL =
  '[data-testid^="home-vendor-"],[data-testid^="home-brand-"],[data-testid^="showcase-"],[data-testid="home-review"],[data-testid="price-ticker"],[data-testid="utility-strip"]';
// Proper nouns and brand names that are correctly untranslated in every locale.
const ALLOWED =
  "milk\\.in|agricoins|whatsapp|npop|pgs|usda|otp|oneuni|pvt|ltd|theorganic|agri\\.in|salem|dharmapuri|tiruppur|coimbatore|chennai|erode|madurai";

const browser = await chromium.launch();
const report = {};

/** One isolated page: own context (no NEXT_LOCALE bleed), service worker
 * blocked (its activation re-navigates), and a hard assertion that the page
 * actually rendered before any probe runs. */
async function withPage(url, width, fn) {
  resetCaps();
  const ctx = await browser.newContext({ serviceWorkers: "block" });
  const page = await ctx.newPage();
  // AuthCluster's silent-SSO probe navigates the TOP-LEVEL window to the
  // AgriID IdP (:3003) with prompt=none. That app is not part of this
  // verification, and with it down the navigation lands on
  // chrome-error://chromewebdata — blanking the page a moment after it
  // renders. Blocking the probe keeps the run about the home page.
  // 204, not abort(): a 204 to a top-level navigation means "stay where you
  // are", whereas aborting it leaves the tab on the error page just the same.
  await page.route("**/api/auth/login*", (route) =>
    route.fulfill({ status: 204, body: "" }),
  );
  const errors = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text().slice(0, 160));
  });
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  await page.setViewportSize({ width, height: 900 });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-testid="category-bar"]', { timeout: 20000 });
  const loaded = await page.evaluate(() => ({
    url: location.href,
    sections: document.querySelectorAll("[data-testid]").length,
    headings: document.querySelectorAll("h1,h2").length,
  }));
  if (!loaded.url.startsWith("http") || loaded.sections < 10 || loaded.headings < 5) {
    throw new Error(`page did not render: ${url} @${width} -> ${JSON.stringify(loaded)}`);
  }
  const result = await fn(page, loaded);
  // Re-assert AFTER the work: a page that blanks midway (silent SSO, a service
  // worker, a redirect) yields empty probes and blank screenshots that look
  // exactly like a clean pass.
  const still = await page.evaluate(() => ({
    url: location.href,
    sections: document.querySelectorAll("[data-testid]").length,
  }));
  if (!still.url.startsWith("http") || still.sections < 10) {
    throw new Error(`page blanked during capture: ${url} @${width} -> ${JSON.stringify(still)}`);
  }
  await ctx.close();
  return { result, errors };
}

for (const [locale, path] of LOCALES) {
  report[locale] = { consoleErrors: [], untranslatedChrome: [], sections: 0 };

  for (const width of [360, 1440]) {
    const { result, errors } = await withPage(`${BASE}${path}`, width, async (page, loaded) => {
      await page.evaluate(() => document.fonts.ready);
      await page.addStyleTag({ content: "*{animation-play-state:paused!important}" });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: `${OUT}/live-${locale}-${width}.png`,
        fullPage: width === 1440,
      });
      if (width !== 1440) return { sections: loaded.sections };
      return {
        sections: loaded.sections,
        untranslated: await page.evaluate(PROBE, {
          dataSel: DATA_SEL,
          allowedSource: ALLOWED,
        }),
      };
    });
    report[locale].consoleErrors.push(...errors);
    report[locale].sections = result.sections;
    if (result.untranslated) report[locale].untranslatedChrome = result.untranslated;
  }
  // 401s on the auth/coins/notify probes are the CORRECT logged-out response,
  // not a defect — collapse them so real errors stand out.
  report[locale].consoleErrors = [
    ...new Set(report[locale].consoleErrors.filter((e) => !/401 \(Unauthorized\)/.test(e))),
  ];
}

// NN5: the category bar must never wrap at any viewport 320-1920.
const wraps = [];
for (const width of [320, 360, 414, 480, 640, 768, 1024, 1280, 1440, 1600, 1920]) {
  const { result } = await withPage(BASE, width, (page) =>
    // A wrapped row shows up as a taller bar. Comparing child `top` values is
    // too sensitive: the active item carries a 2px underline with a negative
    // margin, so it legitimately sits a pixel off its neighbours on ONE row.
    page.evaluate(() => {
      const bar = document.querySelector('[data-testid="category-bar"]');
      const kids = [...bar.firstElementChild.children];
      const boxes = kids.map((k) => k.getBoundingClientRect());
      const top = Math.min(...boxes.map((b) => b.top));
      const bottom = Math.max(...boxes.map((b) => b.bottom));
      const tallest = Math.max(...boxes.map((b) => b.height));
      return {
        barHeight: Math.round(bar.getBoundingClientRect().height),
        items: kids.length,
        contentRows: Math.round(((bottom - top) / tallest) * 10) / 10,
      };
    }),
  );
  wraps.push({ width, ...result });
}
report.categoryBar = {
  perWidth: wraps,
  wrapsAt: wraps.filter((w) => w.contentRows > 1.05).map((w) => w.width),
};

await browser.close();
console.log(JSON.stringify(report, null, 1));
