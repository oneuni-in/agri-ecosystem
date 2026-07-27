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
          matchingUrlPattern: "^https?://[^/]+/$",
          assertions: {
            "categories:performance": ["error", { minScore: 0.9, aggregationMethod: "median-run" }],
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
          // perf floor 0.80, owner-approved 2026-07-27 (D28b). First CI
          // measurement was 0.82 / 0.83 / 0.83 - stable, not runner variance,
          // so 0.90 would fail deterministically rather than flakily. The cost
          // is the shared shell, not the listings: LCP render delay 3664ms of
          // a ~4.0s LCP, of which render-blocking CSS is 1559ms across two
          // small stylesheets (each request costs a ~560ms round trip on this
          // 3G profile); CLS is 0 and TTFB 40ms. 0.80 leaves ~3pts headroom so
          // the gate protects against regressions TODAY; raising it to the
          // Constitution's 0.90 is tracked as a follow-up (critical-CSS
          // delivery + font strategy in packages/ui). a11y/seo hold the full
          // floor - they measure 0.96 / 1.00.
          matchingUrlPattern: "/[a-z][a-z-]*/\\d{6}$",
          assertions: {
            "categories:performance": ["error", { minScore: 0.8, aggregationMethod: "median-run" }],
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
