// A-U3 captures — the content surfaces at the four NN viewports, plus the
// EN/TA/HI sweep on one content page.
//
// Guest-only: /knowledge, /knowledge/[slug] and the home's §11 row are all
// public reads, so this script needs no OTP and costs nothing from the
// 5/day phone budget (unlike capture-u2.mjs).
//
// Locale comes from the NEXT_LOCALE cookie — web-agri has no /ta URL
// segment (i18n/request.ts). One browser CONTEXT per locale, never a
// cookie swap inside one context: the U1 trap was that Next caches the
// resolved locale per render and a mid-context swap silently captures the
// previous language.
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const OUT = process.env.OUT_DIR ?? "docs/design-reference/a-u3";
const AGRI = process.env.AGRI_URL ?? "http://localhost:3002";
const WIDTHS = [360, 768, 1024, 1440];
const LOCALES = ["en", "ta", "hi"];

mkdirSync(OUT, { recursive: true });

/** The newest approved item, so the detail capture is never a 404. */
async function newestSlug() {
  const api = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
  const res = await fetch(`${api}/content/feed?limit=1`);
  const body = await res.json();
  return body.items[0]?.slug ?? null;
}

async function shoot(context, path, name) {
  const page = await context.newPage();
  // Never networkidle (the standing e2e rule) — an ISR revalidation or a
  // long-poll can keep the network busy forever.
  await page.goto(`${AGRI}${path}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("load");
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
  await page.close();
}

const browser = await chromium.launch();
const slug = await newestSlug();
if (!slug) {
  console.error("no approved content — run scripts.content_approve first");
  process.exit(1);
}

// Width sweep, English.
for (const width of WIDTHS) {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  await context.addCookies([
    { name: "NEXT_LOCALE", value: "en", url: AGRI },
    // 641001 Coimbatore — the pincode A-U2 verified the Today strip on.
    { name: "agri_loc", value: JSON.stringify({ pincode: "641001" }), url: AGRI },
  ]);
  await shoot(context, "/knowledge", `knowledge-${width}`);
  await shoot(context, `/knowledge/${slug}`, `knowledge-item-${width}`);
  await shoot(context, "/", `home-knowledge-${width}`);
  await shoot(context, "/schemes", `schemes-${width}`);
  await shoot(context, "/helplines", `helplines-${width}`);
  await context.close();
  console.log(`captured ${width}`);
}

// Locale sweep at 390 (the reference mobile width) — one context each.
for (const locale of LOCALES) {
  const context = await browser.newContext({ viewport: { width: 390, height: 900 } });
  await context.addCookies([{ name: "NEXT_LOCALE", value: locale, url: AGRI }]);
  await shoot(context, "/knowledge", `knowledge-390-${locale}`);
  await shoot(context, "/schemes", `schemes-390-${locale}`);
  await shoot(context, "/helplines", `helplines-390-${locale}`);
  await context.close();
  console.log(`captured ${locale}`);
}

await browser.close();
console.log(`done -> ${OUT}`);
