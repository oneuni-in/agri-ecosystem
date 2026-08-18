// `pnpm perf:home` — the repeatable agri home performance measurement (A-U4 W0).
//
// WHY THIS EXISTS: AG-A34 closed with a WATCH ITEM — the agri home's Lighthouse
// perf swung 0.66–0.95 and 0.76–0.94 across two CI runs while /categories held
// 0.95–0.97. A score you can only observe by reading a CI log after the fact is
// not a number you can engineer against. This makes the measurement a one-liner
// and prints the DISTRIBUTION plus the per-metric breakdown, because "the score
// moved" is not a diagnosis — "TBT moved 600ms and dragged the 30%-weighted
// metric" is.
//
// It drives the Lighthouse NODE API rather than the `lighthouse` CLI on purpose:
// the CLI's Chrome teardown throws EPERM on Windows (the D10-recorded gap that
// made AG-A34 "not verifiable on this machine"), and that throw happens AFTER
// the run's results are already in hand. Owning the launch/kill lets us keep the
// results and swallow a teardown race that has no bearing on the measurement.
//
// Throttling is READ FROM lighthouserc.cjs, never re-declared here: a local
// number that was produced under different throttling than the CI gate is a
// number that lies. One source of truth, so the two cannot drift.
//
// Usage:
//   pnpm perf:home                       # 5 runs on http://localhost:3002/
//   pnpm perf:home --runs 3 --url .../   # explicit
//   pnpm perf:home --json out.json       # machine-readable artifact
//   pnpm perf:home --threshold 0.9       # exit 1 if ANY run is below it
import { createRequire } from "node:module";
import { writeFileSync } from "node:fs";

import * as chromeLauncher from "chrome-launcher";
import lighthouse from "lighthouse";

const require = createRequire(import.meta.url);
// Single source of truth for throttling/emulation — see header note.
const { settings: CI_SETTINGS } = require("../lighthouserc.cjs").ci.collect;

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const URL = arg("url", "http://localhost:3002/");
const RUNS = Number(arg("runs", "5"));
const THRESHOLD = Number(arg("threshold", "0.9"));
const JSON_OUT = arg("json", null);
const LABEL = arg("label", "HEAD");

/** The five metrics the perf score is computed from, with their Lighthouse 12
 * weights — printed so a regression can be attributed to a metric, not guessed
 * at. TBT at 30% is the single heaviest, which is why hydration cost shows up
 * as score volatility. */
const METRICS = [
  ["first-contentful-paint", "FCP", 0.1],
  ["speed-index", "SI", 0.1],
  ["largest-contentful-paint", "LCP", 0.25],
  ["total-blocking-time", "TBT", 0.3],
  ["cumulative-layout-shift", "CLS", 0.25],
];

function fmt(id, audit) {
  if (!audit) return "—";
  const v = audit.numericValue ?? 0;
  return id === "cumulative-layout-shift" ? v.toFixed(3) : `${Math.round(v)}ms`;
}

function stats(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return {
    min: sorted[0],
    max: sorted[sorted.length - 1],
    median:
      sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2,
  };
}

async function runOnce(runIndex) {
  // A FRESH Chrome per run. Reusing one instance lets run N's warmed caches,
  // JIT state and GC pressure leak into run N+1 — which is precisely the kind
  // of hidden coupling that produces an unexplainable distribution.
  const chrome = await chromeLauncher.launch({
    chromeFlags: ["--headless=new", "--no-sandbox", "--disable-gpu"],
  });
  try {
    const result = await lighthouse(
      URL,
      { port: chrome.port, output: "json", logLevel: "error" },
      { extends: "lighthouse:default", settings: CI_SETTINGS },
    );
    const lhr = result.lhr;
    if (lhr.runtimeError) {
      throw new Error(`${lhr.runtimeError.code}: ${lhr.runtimeError.message}`);
    }
    return {
      run: runIndex + 1,
      score: lhr.categories.performance.score,
      metrics: Object.fromEntries(
        METRICS.map(([id, short]) => [short, fmt(id, lhr.audits[id])]),
      ),
      raw: Object.fromEntries(
        METRICS.map(([id, short]) => [
          short,
          lhr.audits[id]?.numericValue ?? null,
        ]),
      ),
    };
  } finally {
    // The EPERM teardown race lives here and ONLY here. The run's results are
    // already returned above, so a failure to reap the temp profile is noise —
    // it must never invalidate a measurement or abort the remaining runs.
    try {
      await chrome.kill();
    } catch (err) {
      if (err?.code !== "EPERM") throw err;
    }
  }
}

const results = [];
console.log(`\nperf:home — ${URL}  (${RUNS} runs, label "${LABEL}")`);
console.log(
  `throttling: ${CI_SETTINGS.throttling.rttMs}ms RTT · ` +
    `${CI_SETTINGS.throttling.cpuSlowdownMultiplier}x CPU · ` +
    `${CI_SETTINGS.formFactor} — from lighthouserc.cjs\n`,
);

for (let i = 0; i < RUNS; i++) {
  const r = await runOnce(i);
  results.push(r);
  const cells = METRICS.map(([, s]) => `${s} ${r.metrics[s]}`).join("  ");
  console.log(
    `  run ${r.run}  score ${r.score.toFixed(2)}  ${r.score >= THRESHOLD ? "✅" : "❌"}   ${cells}`,
  );
}

const scores = results.map((r) => r.score);
const s = stats(scores);
const worst = Math.min(...scores);
const below = results.filter((r) => r.score < THRESHOLD);

console.log(`\n  distribution  min ${s.min.toFixed(2)} · median ${s.median.toFixed(
  2,
)} · max ${s.max.toFixed(2)}`);
console.log(`  WORST SAMPLE  ${worst.toFixed(2)}   (threshold ${THRESHOLD})`);

// Per-metric spread: this is the diagnostic payload. A score that swings while
// every metric is steady would mean the harness is lying; in practice one
// metric owns the variance and this names it.
console.log("\n  per-metric spread across runs:");
for (const [, short] of METRICS) {
  const vals = results.map((r) => r.raw[short]).filter((v) => v !== null);
  if (!vals.length) continue;
  const m = stats(vals);
  const isCls = short === "CLS";
  const f = (v) => (isCls ? v.toFixed(3) : `${Math.round(v)}ms`);
  console.log(
    `    ${short.padEnd(4)} min ${f(m.min).padStart(8)} · median ${f(m.median).padStart(8)} · max ${f(m.max).padStart(8)}   (spread ${f(m.max - m.min)})`,
  );
}

if (JSON_OUT) {
  writeFileSync(
    JSON_OUT,
    JSON.stringify({ url: URL, label: LABEL, threshold: THRESHOLD, results }, null, 2),
  );
  console.log(`\n  wrote ${JSON_OUT}`);
}

if (below.length) {
  console.log(
    `\n❌ ${below.length}/${RUNS} run(s) below ${THRESHOLD}: ${below
      .map((r) => `run ${r.run} (${r.score.toFixed(2)})`)
      .join(", ")}\n`,
  );
  process.exit(1);
}
console.log(`\n✅ all ${RUNS} runs ≥ ${THRESHOLD}\n`);
