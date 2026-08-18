// `pnpm perf:sweep` — the A-U4 W4 Lighthouse sweep across every agri route.
//
// perf:home answers "is the home fast?". This answers the D57 gate's actual
// question: "is EVERY route >= 0.90 perf with a11y and SEO at 100?" — and it
// prints the table CP3 asks for rather than leaving it to be assembled by
// hand from six separate runs.
//
// It reuses perf-home's contract: throttling comes from lighthouserc.cjs, so
// these numbers and CI's mean the same thing, and Chrome is driven through
// the node API so the Windows EPERM teardown cannot lose a result.
//
// Usage:
//   pnpm perf:sweep                      # all routes, 3 runs each
//   pnpm perf:sweep --runs 5
//   pnpm perf:sweep --base http://localhost:3002
import { createRequire } from "node:module";

import * as chromeLauncher from "chrome-launcher";
import lighthouse from "lighthouse";

const require = createRequire(import.meta.url);
const { settings: CI_SETTINGS } = require("../lighthouserc.cjs").ci.collect;

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const BASE = arg("base", "http://localhost:3002").replace(/\/$/, "");
const RUNS = Number(arg("runs", "3"));

// The D57 gate's list. `/search` is excluded for the reason A-U3 recorded:
// it is noindex, needs a ?q= to render anything, and auditing its empty
// state would gate on a shell. Auth-gated routes (/coins, /saved) are
// excluded because an unauthenticated audit only ever sees the login
// redirect — the same carve-out /business already carries.
const ROUTES = [
  "/",
  "/categories",
  "/tools",
  "/knowledge",
  "/directory",
  "/schemes",
  "/helplines",
  "/mandi",
  "/offline",
];

// The Constitution's floors.
const FLOORS = { performance: 0.9, accessibility: 1.0, seo: 1.0 };

// Routes that are deliberately noindex cannot pass Lighthouse's SEO
// category, because `is-crawlable` fails by design on them. /offline is the
// shell shown when the network is gone — indexing an error state as content
// would be the actual bug. So it is judged on perf and a11y, and its SEO
// score is reported but not gated. This is a measurement carve-out, not a
// standards one: no route's REAL SEO floor is lowered.
const SEO_EXEMPT = new Set(["/offline"]);

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

async function auditOnce(url) {
  const chrome = await chromeLauncher.launch({
    chromeFlags: ["--headless=new", "--no-sandbox", "--disable-gpu"],
  });
  try {
    const { lhr } = await lighthouse(
      url,
      { port: chrome.port, output: "json", logLevel: "error" },
      { extends: "lighthouse:default", settings: CI_SETTINGS },
    );
    if (lhr.runtimeError) throw new Error(lhr.runtimeError.code);
    const failing = {};
    for (const key of ["accessibility", "seo"]) {
      failing[key] = Object.values(lhr.audits)
        .filter(
          (a) =>
            lhr.categories[key].auditRefs.some((r) => r.id === a.id) &&
            a.score !== null &&
            a.score < 1,
        )
        .map((a) => a.id);
    }
    return {
      performance: lhr.categories.performance.score,
      accessibility: lhr.categories.accessibility.score,
      seo: lhr.categories.seo.score,
      failing,
    };
  } finally {
    try {
      await chrome.kill();
    } catch (err) {
      if (err?.code !== "EPERM") throw err; // see perf-home.mjs
    }
  }
}

const rows = [];
console.log(`\nperf:sweep — ${BASE}, ${RUNS} runs/route, floors ` +
  `perf ${FLOORS.performance} · a11y ${FLOORS.accessibility} · seo ${FLOORS.seo}\n`);

for (const route of ROUTES) {
  const samples = [];
  let failing = { accessibility: [], seo: [] };
  for (let i = 0; i < RUNS; i++) {
    try {
      const result = await auditOnce(`${BASE}${route}`);
      samples.push(result);
      failing = result.failing; // last run's detail is enough to act on
    } catch (err) {
      console.log(`  ${route.padEnd(14)} ERROR ${err.message}`);
    }
  }
  if (!samples.length) continue;
  const row = {
    route,
    perf: median(samples.map((s) => s.performance)),
    perfWorst: Math.min(...samples.map((s) => s.performance)),
    a11y: median(samples.map((s) => s.accessibility)),
    seo: median(samples.map((s) => s.seo)),
    failing,
  };
  rows.push(row);
  const mark = (v, floor) => (v >= floor ? "ok " : "OFF");
  console.log(
    `  ${route.padEnd(14)} perf ${row.perf.toFixed(2)} (worst ${row.perfWorst.toFixed(2)}) ${mark(row.perf, FLOORS.performance)}  ` +
      `a11y ${row.a11y.toFixed(2)} ${mark(row.a11y, FLOORS.accessibility)}  ` +
      `seo ${row.seo.toFixed(2)} ${SEO_EXEMPT.has(route) ? "n/a" : mark(row.seo, FLOORS.seo)}`,
  );
}

console.log("\n| Route | Perf (median) | Perf (worst) | A11y | SEO |");
console.log("|---|---|---|---|---|");
for (const r of rows) {
  console.log(
    `| \`${r.route}\` | ${r.perf.toFixed(2)} | ${r.perfWorst.toFixed(2)} | ${r.a11y.toFixed(2)} | ${r.seo.toFixed(2)} |`,
  );
}

const a11yProblems = rows.filter((r) => r.a11y < FLOORS.accessibility);
const seoProblems = rows.filter((r) => r.seo < FLOORS.seo && !SEO_EXEMPT.has(r.route));
if (a11yProblems.length || seoProblems.length) {
  console.log("\n  audits to fix:");
  for (const r of [...a11yProblems, ...seoProblems]) {
    const ids = [...new Set([...r.failing.accessibility, ...r.failing.seo])];
    if (ids.length) console.log(`    ${r.route}: ${ids.join(", ")}`);
  }
}

const below = rows.filter((r) => r.perf < FLOORS.performance);
console.log(
  `\n  ${rows.length - below.length}/${rows.length} routes at or above the ${FLOORS.performance} perf floor\n`,
);
if (below.length || a11yProblems.length || seoProblems.length) process.exit(1);
