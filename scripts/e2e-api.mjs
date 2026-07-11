/**
 * Playwright webServer command for the FastAPI side: run migrations, then
 * uvicorn with the E2E peek flag. Uses the venv python locally (Windows dev
 * box) and plain `python` on CI (the job pip-installs into the runner env).
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

const server = spawn(
  python,
  ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
  { cwd: core, env, stdio: "inherit" },
);
server.on("exit", (code) => process.exit(code ?? 0));
