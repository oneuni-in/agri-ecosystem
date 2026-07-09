// Placeholder generator wired for D01-B.
//
// Once backend/openapi.json exists this shells out to openapi-typescript and
// writes src/generated/openapi.ts. Until then it no-ops with exit 0 so that a
// fresh clone's `pnpm gen:types` is green rather than a confusing ENOENT.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const schema = resolve(here, "../../../backend/openapi.json");
const out = resolve(here, "../src/generated/openapi.ts");

if (!existsSync(schema)) {
  console.log(
    `[@agri/types] no OpenAPI schema at ${schema} yet — skipping.\n` +
      `[@agri/types] D01-B (FastAPI skeleton) emits it; re-run then.`,
  );
  process.exit(0);
}

mkdirSync(dirname(out), { recursive: true });

const result = spawnSync(
  "openapi-typescript",
  [schema, "-o", out],
  { stdio: "inherit", shell: true },
);

process.exit(result.status ?? 1);
