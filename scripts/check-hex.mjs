// Bans raw color literals outside packages/config (CLAUDE.md: tokens only).
// Scans apps/ and packages/ui/ source for hex or rgb()/rgba() literals.
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

const ROOTS = ["apps", "packages/ui"];
const EXTS = [".ts", ".tsx", ".css"];
const SKIP = new Set(["node_modules", ".next", ".turbo", "dist"]);
const COLOR = /#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b|rgba?\(/;

const violations = [];

function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (SKIP.has(entry.name)) continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(path);
      continue;
    }
    if (!EXTS.some((ext) => entry.name.endsWith(ext))) continue;
    readFileSync(path, "utf8")
      .split("\n")
      .forEach((line, i) => {
        if (COLOR.test(line)) {
          violations.push(`${relative(".", path)}:${i + 1}  ${line.trim()}`);
        }
      });
  }
}

ROOTS.forEach(walk);

if (violations.length > 0) {
  console.error(
    `check:hex FAILED — ${violations.length} raw color literal(s); use preset tokens:\n`,
  );
  for (const v of violations) console.error("  " + v);
  process.exit(1);
}
console.log("check:hex OK — no raw color literals in apps/ or packages/ui/");
