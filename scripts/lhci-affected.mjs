// Lighthouse gate orchestrator (SPEC D04-C, non-negotiable #2).
//
// 1. Asks turbo which apps' `build` is affected vs the base ref
//    (BASE_REF env, e.g. origin/dev on PRs; falls back to ALL apps).
// 2. Always includes web-agri — its /demo route is the D02 design-system
//    template and must never regress.
// 3. Builds the affected apps (turbo-cached), serves each `next start` on its
//    fixed port, waits for readiness, then runs `lhci autorun` (config +
//    thresholds + budgets live in lighthouserc.cjs) against home pages
//    + /demo. Exit code is lhci's.
//
// Works identically locally: `node scripts/lhci-affected.mjs`.
import { execFileSync, spawn } from "node:child_process";

const APPS = {
  "web-milk": 3000,
  "web-organic": 3001,
  "web-agri": 3002,
  "web-id": 3003,
  "web-admin": 3004,
};
const ALWAYS = "web-agri";
const READY_TIMEOUT_MS = 120_000;

// web-admin (3004) is the internal, auth-gated admin console (U3) — not a
// public SEO surface. Its root layout resolves the session server-side on
// every route (AdminChrome -> auth.getServerUser()), which in a production
// `next start` with no AUTH_SESSION_SECRET fails the auth-client prod-secret
// guard on the first request, so `/` 500s and never becomes "ready" — an
// unauthenticated LHCI run cannot meaningfully audit it and would only ever
// fail the gate for the wrong reason. The admin routes get the documented
// Lighthouse carve-out (polish-u1 §7.4/§8; an authenticated admin LHCI run is
// the standing follow-up). auth-client is consumed, not owned, so the fix is
// here — never audit web-admin in this unauthenticated gate.
const AUDIT_EXCLUDE = new Set(["web-admin"]);

// Non-home routes that must also hold the floor. The D28 pincode landing is
// milk.in's actual SEO surface (home is a pincode box; these pages are what
// Google indexes), so it cannot be left ungated. It is dynamic SSR reading
// covers(), so it needs the API up — without a backend it renders notFound()
// and would fail the audit for the wrong reason. Included only when the API
// answers; the skip is logged, never silent.
const EXTRA_URLS = {
  "web-milk": ["/coimbatore/641001"], // seeded covered pincode (seed_e2e_milk.py)
  // A-U1 AG-A8: /categories holds the 0.90 floor alongside the agri home —
  // it is the registry surface every Soon tile funnels through. Its grid is
  // GET /catalog/verticals, so it rides the same api-up gate below: without
  // a backend the registry read is empty and the audit would score a shell.
  "web-agri": ["/categories"],
};
const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

function run(cmd, args, opts = {}) {
  return execFileSync(cmd, args, { encoding: "utf8", shell: process.platform === "win32", ...opts });
}

function affectedApps() {
  const base = process.env.BASE_REF;
  if (!base) {
    console.log("lhci: no BASE_REF set - auditing all apps");
    return Object.keys(APPS);
  }
  try {
    const dry = JSON.parse(
      run("pnpm", ["exec", "turbo", "run", "build", `--filter=...[${base}]`, "--dry=json"]),
    );
    const affected = (dry.tasks ?? [])
      .filter((t) => t.task === "build" && t.package.startsWith("@agri/web-"))
      .map((t) => t.package.replace("@agri/", ""));
    return [...new Set(affected)];
  } catch (error) {
    console.warn(`lhci: turbo dry-run vs ${base} failed (${error.message}) - auditing all apps`);
    return Object.keys(APPS);
  }
}

async function waitForReady(url) {
  const deadline = Date.now() + READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // server not up yet
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`server at ${url} not ready after ${READY_TIMEOUT_MS / 1000}s`);
}

function kill(child) {
  if (child.exitCode !== null) return;
  if (process.platform === "win32") {
    // next start forks workers; kill the whole tree
    try {
      execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    } catch {
      /* already gone */
    }
  } else {
    child.kill("SIGTERM");
  }
}

const apps = [...new Set([...affectedApps(), ALWAYS])].filter(
  (app) => app in APPS && !AUDIT_EXCLUDE.has(app),
);
console.log(`lhci: auditing apps: ${apps.join(", ")}`);

const filters = apps.flatMap((app) => [`--filter=@agri/${app}`]);
run("pnpm", ["exec", "turbo", "run", "build", ...filters], { stdio: "inherit" });

const urls = apps.map((app) => `http://localhost:${APPS[app]}/`);
if (apps.includes(ALWAYS)) urls.push(`http://localhost:${APPS[ALWAYS]}/demo`);

const apiUp = await fetch(`${API_BASE_URL}/health`)
  .then((r) => r.ok)
  .catch(() => false);
for (const [app, paths] of Object.entries(EXTRA_URLS)) {
  if (!apps.includes(app)) continue;
  if (!apiUp) {
    console.warn(
      `lhci: SKIPPING ${app} extra URLs (${paths.join(", ")}) - no API at ${API_BASE_URL}. ` +
        `These routes are NOT audited in this run.`,
    );
    continue;
  }
  urls.push(...paths.map((p) => `http://localhost:${APPS[app]}${p}`));
}

const servers = apps.map((app) =>
  spawn("pnpm", ["--filter", `@agri/${app}`, "start"], {
    stdio: "ignore",
    shell: process.platform === "win32",
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
  }),
);

let exitCode = 1;
try {
  await Promise.all(apps.map((app) => waitForReady(`http://localhost:${APPS[app]}/`)));
  // warm every audited URL (not just home pages): the first SSR render pays
  // one-off costs that would otherwise land inside the first lighthouse run
  await Promise.all(urls.map((url) => fetch(url).catch(() => {})));
  run("pnpm", ["exec", "lhci", "autorun", "--config=lighthouserc.cjs"], {
    stdio: "inherit",
    env: { ...process.env, LHCI_URLS: urls.join(",") },
  });
  exitCode = 0;
} catch (error) {
  console.error(`lhci: FAILED - ${error.message}`);
} finally {
  servers.forEach(kill);
}
process.exit(exitCode);
