/**
 * AG-A12 — prove the farm calculators COMPUTE with the network switched off.
 *
 * WHY THIS EXISTS INSTEAD OF AN E2E SPEC. e2e/agri-pwa.spec.ts can prove that
 * /tools comes back offline as the real page, and stops there. The e2e harness
 * runs `next dev`, which serves /_next/static/chunks/* with
 * `Cache-Control: no-store, must-revalidate` — an instruction to the browser
 * NOT to keep them. Offline there is nothing to hydrate from, every input sits
 * at its default (650000 / 12.5% / 84 months -> ₹11,649), and no timeout or
 * selector can reach past that. It is the dev server's design, not a flake.
 *
 * A production build serves those chunks immutable, so one real visit leaves
 * them in the HTTP cache and hydration survives the network going away. That
 * is a different build, so it needs its own run — the same reason the perf
 * work grew scripts/perf-home.mjs rather than trusting a dev-mode number.
 *
 * WHAT IT PROVES, EXACTLY: a visitor who has opened /tools once, and then
 * loses signal, can still work out an EMI. It does NOT prove anything about a
 * visitor who has never opened /tools — that person correctly gets the
 * /offline shell, because the service worker runtime-caches this route rather
 * than precaching it (see public/sw.js for why a precached-but-dead
 * calculator is worse than an honest shell).
 *
 *   node scripts/verify-offline-tools.mjs
 *
 * Exit 0 = computed offline. Exit 1 = did not.
 */
import { spawn, spawnSync } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

import { chromium } from "playwright";

const PORT = 3002;
const BASE = `http://localhost:${PORT}`;
// The same fixture the online spec uses, so a difference between them is a
// difference in OFFLINE behaviour and nothing else.
const FIXTURE = { principal: "100000", rate: "11", months: "60", expected: "₹2,174" };
const DEFAULTS_IF_DEAD = "₹11,649"; // what a non-hydrated page shows

function run(cmd, args) {
  const res = spawnSync(cmd, args, { stdio: "inherit", shell: process.platform === "win32" });
  if (res.status !== 0) {
    console.error(`\n${cmd} ${args.join(" ")} failed (${res.status})`);
    process.exit(res.status ?? 1);
  }
}

async function waitForServer(url, timeoutMs = 180_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(4000) });
      if (res.ok) return true;
    } catch {
      /* not up yet */
    }
    await sleep(1500);
  }
  return false;
}

console.log("AG-A12 offline-compute proof — PRODUCTION build\n");
console.log("1/4  building web-agri (dev-mode chunks are no-store; only a prod build can hydrate offline)");
run("pnpm", ["--filter", "@agri/web-agri", "build"]);

console.log("\n2/4  starting the production server");
const server = spawn("pnpm", ["--filter", "@agri/web-agri", "start"], {
  stdio: "ignore",
  shell: process.platform === "win32",
  detached: false,
});

let browser;
let failed = true;
try {
  if (!(await waitForServer(`${BASE}/tools`))) {
    console.error(`production server never answered on ${BASE}/tools`);
    process.exit(1);
  }

  console.log("3/4  one real online visit, then the network goes away");
  browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto(`${BASE}/tools`, { waitUntil: "load" });
  // The worker must be controlling this page before its cache can serve it.
  await page.waitForFunction(() => navigator.serviceWorker?.controller !== null, undefined, {
    timeout: 60_000,
  });
  await page.waitForLoadState("networkidle");

  // A SECOND visit, still online, and it is not padding. The worker only
  // caches what its own fetch handler sees, and the first navigation of a
  // session is served BEFORE the worker controls the page — so that one is
  // invisible to it and caches nothing. Runtime-cached means "held after the
  // visitor has actually been here while the worker was running", and this
  // is that visit. Without it the offline navigation correctly falls through
  // to the /offline shell, which is the worker behaving properly, not a bug.
  await page.goto(`${BASE}/tools`, { waitUntil: "load" });
  await page.waitForLoadState("networkidle");

  await context.setOffline(true);
  await page.goto(`${BASE}/tools`).catch(() => undefined);

  console.log("4/4  computing with the network off");
  await page.getByLabel(/loan amount/i).fill(FIXTURE.principal);
  await page.getByLabel(/interest rate/i).fill(FIXTURE.rate);
  await page.getByLabel(/tenure/i).fill(FIXTURE.months);

  const result = await page
    .getByTestId("emi-result")
    .textContent({ timeout: 15_000 })
    .then((t) => (t ?? "").trim());

  console.log(
    `\n  ${FIXTURE.principal} @ ${FIXTURE.rate}% over ${FIXTURE.months}m  ->  ${result}`,
  );

  if (result === FIXTURE.expected) {
    console.log(`  PASS — computed ${result} offline. AG-A12 holds on a production build.`);
    failed = false;
  } else if (result === DEFAULTS_IF_DEAD) {
    console.error(
      `  FAIL — got ${result}, which is the form's DEFAULT state. The page came back\n` +
        "         offline but never hydrated, so the inputs did nothing. A calculator\n" +
        "         that looks alive and is not is worse than the offline shell.",
    );
  } else {
    console.error(`  FAIL — expected ${FIXTURE.expected}, got ${result}.`);
  }
} finally {
  if (browser) {
    // Windows teardown throws EPERM on a browser that has already gone; that
    // must not lose an otherwise good result (perf-home.mjs, same lesson).
    try {
      await browser.close();
    } catch (err) {
      if (err?.code !== "EPERM") throw err;
    }
  }
  // server.kill() alone LEAKS on Windows: `pnpm` is spawned through a shell,
  // so the signal reaches the shell and the actual Next server keeps the port.
  // A leaked PRODUCTION server on :3002 then gets silently adopted by
  // Playwright's `reuseExistingServer`, and the whole e2e suite quietly runs
  // against the wrong build — which is exactly what happened once. Kill the
  // tree, and verify the port is really free rather than assuming.
  if (process.platform === "win32" && server.pid) {
    spawnSync("taskkill", ["/PID", String(server.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    server.kill();
  }
  try {
    await fetch(`${BASE}/tools`, { signal: AbortSignal.timeout(2500) });
    console.error(`
  WARNING: something is still serving ${BASE} — kill it before running e2e.`);
  } catch {
    /* port free, as intended */
  }
}

process.exit(failed ? 1 : 0);
