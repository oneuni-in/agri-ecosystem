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
//
// M5 Task 17 (NN1 e2e - e2e/advertiser-selfserve.spec.ts): the Razorpay test
// stub (modules/billing/razorpay_client.py) short-circuits create_payment_link/
// fetch_payment/fetch_payment_link to canned responses BEFORE any network
// call, so the full create -> pay(test) -> approve -> serve walk runs with
// zero real Razorpay credentials. APP_ENV is pinned to "dev" explicitly
// (never inherited from a stray shell env) because the stub is a hard AND
// against app_env != "prod" by design - a misconfigured prod deploy with
// RAZORPAY_TEST_STUB left set must still make real Razorpay calls, never
// canned ones. CONSOLE_BASE_URL matches the Settings default already (web-agri's
// :3002, D01-A) but is set explicitly so the Payment Link callback_url
// (`{console_base_url}/business/ads?paid=...`) never silently drifts from
// where web-agri actually listens. ADS_DELIVERY_LOG_SAMPLE=1.0 makes the
// spec's why-served delivery-log assertions deterministic instead of racing
// the default 10% sample (paid campaigns log unsampled regardless per M5
// Task 13, but house-ad rows other specs rely on stay sampled at the default
// unless overridden - 1.0 here is safe since e2e never asserts a NEGATIVE
// on delivery-log volume).
const env = {
  ...process.env,
  OTP_TEST_PEEK: "true",
  ADS_FREQ_CAP_PER_DAY: "100000",
  APP_ENV: "dev",
  RAZORPAY_TEST_STUB: "true",
  RAZORPAY_WEBHOOK_SECRET: "whsec_e2e",
  CONSOLE_BASE_URL: "http://localhost:3002",
  ADS_DELIVERY_LOG_SAMPLE: "1.0",
};

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
// --enable-billing-flag (M5 Task 17): flips billing_enabled globally for
// this e2e run the same dev/test-only, refused-in-prod way, so
// advertiser-selfserve.spec.ts can drive real ad-order checkout. This is a
// whole-suite side effect - it is what forced e2e/vendor-dashboard.spec.ts's
// former "billing stays dark (404)" assertions to become "billing is live
// (200)" ones; see that spec for the updated assertions.
const houseAds = spawnSync(
  python,
  [
    "scripts/seed_house_ads.py",
    "--enable-flag",
    "--enable-billing-flag",
    "--reset-caps",
    "--with-sponsored-listing",
  ],
  { cwd: core, env, stdio: "inherit" },
);
if (houseAds.status !== 0) process.exit(houseAds.status ?? 1);

// A-U2 W3: the agri Today sections read real engines now that the fixtures
// are deleted, so seed their two REAL inputs — a captured Open-Meteo
// response written into the weather cache, and real Agmarknet rows pushed
// through the real ingest. Without this the home would either call
// Open-Meteo on every CI run (rude, and flaky) or render empty states,
// and e2e/agri-home.spec.ts could assert neither. Idempotent: the cache
// write overwrites and the ingest upserts on its natural key.
const agriSeed = spawnSync(python, ["-m", "scripts.seed_e2e_agri"], {
  cwd: core,
  env,
  stdio: "inherit",
});
if (agriSeed.status !== 0) process.exit(agriSeed.status ?? 1);

const server = spawn(
  python,
  ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
  { cwd: core, env, stdio: "inherit" },
);
server.on("exit", (code) => process.exit(code ?? 0));
