/**
 * Playwright webServer command for the FastAPI side: run migrations, then
 * seed the deterministic D23 milk-home fixture (idempotent — safe on repeat
 * runs / reuseExistingServer), then uvicorn with the E2E peek flag. Uses the
 * venv python locally (Windows dev box) and plain `python` on CI (the job
 * pip-installs into the runner env).
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const core = path.join(repoRoot, "backend", "core");
const venvPython = path.join(core, ".venv", "Scripts", "python.exe");
const python = process.env.CI ? "python" : existsSync(venvPython) ? venvPython : "python";

// ADS_FREQ_CAP_PER_DAY: every request in an e2e run shares one viewer hash
// (same IP + UA, daily window), so the production 3/day serve cap exhausts
// the house placements after ~3 page loads of ANY earlier spec (a11y runs
// before ads-surfaces alphabetically) and every later ad assertion sees the
// fallback. The cap is a fraud control for paid ads; e2e neutralises it.
const env = { ...process.env, OTP_TEST_PEEK: "true", ADS_FREQ_CAP_PER_DAY: "100000" };

const migrate = spawnSync(python, ["-m", "alembic", "upgrade", "head"], {
  cwd: core,
  env,
  stdio: "inherit",
});
if (migrate.status !== 0) process.exit(migrate.status ?? 1);

// geo.states/districts/pincodes ship empty from 0004_geo_v1 (see THREAT/NOTES
// in that migration) — district_for_pincode() resolves nothing without this,
// so every pincode would fall through to scope="out_of_area" regardless of
// vendor coverage. Must run after migrate (needs the schema) and before the
// milk seed (coverage/distance + district resolution both depend on geo).
// Idempotent: shared/geo/loader.py upserts on natural keys (lgd_code /
// pincode) via on_conflict_do_update, so re-running against an already-loaded
// DB is safe.
const geo = spawnSync(python, ["scripts/load_geo.py"], {
  cwd: core,
  env,
  stdio: "inherit",
});
if (geo.status !== 0) process.exit(geo.status ?? 1);

// D23: deterministic milk vendor covering 641001 for the web-milk 'covered'
// empty-state branch (e2e/milk-home.spec.ts). Must run after migrations
// (needs the schema) and before the milk tests navigate; running it here —
// before uvicorn even starts — is simpler than a separate webServer entry
// with a bogus health URL, and this script already owns the migrate-then-run
// sequencing for the API's boot. Idempotent (checks by business name).
const seed = spawnSync(python, ["scripts/seed_e2e_milk.py"], {
  cwd: core,
  env,
  stdio: "inherit",
});
if (seed.status !== 0) process.exit(seed.status ?? 1);

// M2: house-ad fill + ads_enabled so e2e/ads-surfaces.spec.ts is
// deterministic. Idempotent (keyed on campaign name); --enable-flag is
// dev/test-only (refused in prod inside the script).
// --reset-caps: one machine = one viewer hash, so the 3/day serve cap
// exhausts the house placements after a few page loads across specs/runs.
const houseAds = spawnSync(
  python,
  ["scripts/seed_house_ads.py", "--enable-flag", "--reset-caps"],
  { cwd: core, env, stdio: "inherit" },
);
if (houseAds.status !== 0) process.exit(houseAds.status ?? 1);

const server = spawn(
  python,
  ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
  { cwd: core, env, stdio: "inherit" },
);
server.on("exit", (code) => process.exit(code ?? 0));
