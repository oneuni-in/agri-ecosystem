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

const apps = [...new Set([...affectedApps(), ALWAYS])].filter((app) => app in APPS);
console.log(`lhci: auditing apps: ${apps.join(", ")}`);

const filters = apps.flatMap((app) => [`--filter=@agri/${app}`]);
run("pnpm", ["exec", "turbo", "run", "build", ...filters], { stdio: "inherit" });

const urls = apps.map((app) => `http://localhost:${APPS[app]}/`);
if (apps.includes(ALWAYS)) urls.push(`http://localhost:${APPS[ALWAYS]}/demo`);

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
