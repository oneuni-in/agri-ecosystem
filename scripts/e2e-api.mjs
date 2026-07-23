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

const env = { ...process.env, OTP_TEST_PEEK: "true" };

const migrate = spawnSync(python, ["-m", "alembic", "upgrade", "head"], {
  cwd: core,
  env,
  stdio: "inherit",
});
if (migrate.status !== 0) process.exit(migrate.status ?? 1);

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

const server = spawn(
  python,
  ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
  { cwd: core, env, stdio: "inherit" },
);
server.on("exit", (code) => process.exit(code ?? 0));
