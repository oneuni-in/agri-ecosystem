// Lighthouse CI config (SPEC D04-C). URLs are injected by
// scripts/lhci-affected.mjs via LHCI_URLS (comma-separated); the script also
// builds and serves the affected apps. Mobile emulation + throttled 3G-class
// network; category thresholds are the Constitution's non-negotiable floor.
const budgets = require("./budgets.json");

const urls = (process.env.LHCI_URLS || "http://localhost:3002/demo")
  .split(",")
  .map((url) => url.trim())
  .filter(Boolean);

module.exports = {
  ci: {
    collect: {
      url: urls,
      // 3 runs per URL, asserted on the median run: a single run on shared
      // CI VMs swings 15-20 perf points (observed: 0.78 vs 0.99 for the same
      // page); the median is stable without loosening any threshold.
      numberOfRuns: 3,
      settings: {
        // Lighthouse's mobile defaults already emulate a Moto G-class phone;
        // this pins the classic 3G network profile + 4x CPU slowdown.
        formFactor: "mobile",
        screenEmulation: { mobile: true, width: 412, height: 823, deviceScaleFactor: 1.75 },
        // PSI sends "Chrome-Lighthouse" in its UA; local lighthouse 12 does
        // not. Pin the PSI-style UA so Next's htmlLimitedBots list (see
        // next.config.ts) serves blocking in-head metadata to the audit.
        emulatedUserAgent:
          "Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36 Chrome-Lighthouse",
        throttlingMethod: "simulate",
        throttling: {
          rttMs: 150,
          throughputKbps: 1638.4,
          requestLatencyMs: 562.5,
          downloadThroughputKbps: 1474.56,
          uploadThroughputKbps: 675,
          cpuSlowdownMultiplier: 4,
        },
        budgets,
      },
    },
    assert: {
      assertMatrix: [
        {
          // App templates: the Constitution floor, non-negotiable.
          // :3000 (the milk home) is excluded here ONLY because it carries the
          // issue-#59 carve-out below — every other app home stays at 0.90.
          matchingUrlPattern: "^https?://[^/]+:(?!3000/$)\\d+/$",
          assertions: {
            "categories:performance": ["error", { minScore: 0.9, aggregationMethod: "median-run" }],
            "categories:accessibility": ["error", { minScore: 0.95, aggregationMethod: "median-run" }],
            "categories:seo": ["error", { minScore: 0.95, aggregationMethod: "median-run" }],
          },
        },
        {
          // milk.in home — TEMPORARY 0.80 carve-out, issue #59, expiring at
          // the Milk.in launch (launch gates on restoring 0.90; the U1 PR did
          // not). Pre-committed in docs/design-reference/polish-u1.md §5g
          // BEFORE the first CI number existed; the first true measurement of
          // the rebuilt page came in at median 0.87 (0.80/0.87/0.85). The
          // cost is main-thread render delay on the §4 <h1> (measured levers
          // in #59). a11y/SEO stay at the full floor.
          matchingUrlPattern: "^https?://[^/]+:3000/$",
          assertions: {
            "categories:performance": ["error", { minScore: 0.8, aggregationMethod: "median-run" }],
            "categories:accessibility": ["error", { minScore: 0.95, aggregationMethod: "median-run" }],
            "categories:seo": ["error", { minScore: 0.95, aggregationMethod: "median-run" }],
          },
        },
        {
          // D28 pincode landing pages (/{city}/{pincode}) - milk.in's real SEO
          // surface: home is just a pincode box, THESE are what Google indexes
          // and what carries the ItemList/LocalBusiness JSON-LD. Audited only
          // when the API is up (scripts/lhci-affected.mjs), which the CI
          // lighthouse job now provides.
          //
          // History: a 0.80 carve-out (owner-approved 2026-07-27, D28b) for
          // two render-blocking stylesheets was removed when issue #45's
          // `experimental.inlineCss` fix killed that cost and the route
          // passed 0.90 in CI.
          //
          // TEMPORARY 0.85 re-baseline, owner-approved 2026-08-12 (U1b PR
          // #60), expiring with issue #59 at the Milk.in launch. The U1b CI
          // runs measured 0.86/0.83/0.88 - but the PRE-U1b page measured
          // 0.94/0.83/0.89 on the same gate (PR #58's artifact), i.e. the
          // 0.90 floor was only ever cleared here by run-to-run variance.
          // The dominant cost is ~85% LCP render delay on the <h1> - the
          // shared shell's font/hydration pipeline, the SAME structural cost
          // issue #59 tracks on the home; the U1b delta itself is +1KB JS /
          // +10 DOM nodes. Restoring 0.90 here rides #59's launch-gating
          // perf work. a11y/SEO stay at the full floor.
          matchingUrlPattern: "/[a-z][a-z-]*/\\d{6}$",
          assertions: {
            "categories:performance": ["error", { minScore: 0.85, aggregationMethod: "median-run" }],
            "categories:accessibility": ["error", { minScore: 0.95, aggregationMethod: "median-run" }],
            "categories:seo": ["error", { minScore: 0.95, aggregationMethod: "median-run" }],
          },
        },
        {
          // /demo (D02 kitchen-sink gallery): ~138KB of streamed HTML makes
          // LCP track full document download; measured baseline was perf 83 on
          // 3G. SEO is exempt: the page deliberately self-noindexes
          // (noindex-until-populated rule), which zeroes crawlability audits.
          // Deliberate carve-out, approved 2026-07-10 - see PR D04.
          // Re-baselined 0.80 -> 0.75 on 2026-07-24 (owner-approved): the D24
          // PR scored 0.70-0.79 across 6 samples on a byte-identical /demo
          // (no packages/ui or web-agri changes vs dev), i.e. runner/Chrome
          // drift, not a code regression. Real regressions still fail.
          matchingUrlPattern: "/demo$",
          assertions: {
            "categories:performance": ["error", { minScore: 0.75, aggregationMethod: "median-run" }],
            "categories:accessibility": ["error", { minScore: 0.95, aggregationMethod: "median-run" }],
          },
        },
      ],
    },
    // No public upload: reports land in .lhci/ and CI attaches them as a
    // workflow artifact (keeps report URLs/content out of third-party storage).
    upload: { target: "filesystem", outputDir: ".lhci" },
  },
};
