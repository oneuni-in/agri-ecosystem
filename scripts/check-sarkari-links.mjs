#!/usr/bin/env node
/**
 * AG-A11 — sarkari-hub link checker (A-U1 §9b).
 *
 * Reads apps/web-agri/data/sarkari.json (the SAME file data/sarkari.ts
 * serves to the home) and, for every entry:
 *   1. asserts the URL is https and its host ends with the declared
 *      official domain;
 *   2. asserts the declared domain ends with an allowlisted public suffix
 *      (gov.in / nic.in) — we never link a look-alike;
 *   3. resolves the URL (GET, redirects followed, 15s timeout, one retry
 *      for network flakiness) and requires a 2xx.
 *
 * Run at launch prep: `node scripts/check-sarkari-links.mjs`.
 * NOT wired into CI — government portals rate-limit and flake; a red CI
 * from someone else's maintenance window helps no one. Exit 1 lists every
 * failure; exit 0 prints the OK table.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ALLOWED_SUFFIXES = ["gov.in", "nic.in"];
const TIMEOUT_MS = 15_000;

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dataPath = join(root, "apps", "web-agri", "data", "sarkari.json");
const { entries } = JSON.parse(readFileSync(dataPath, "utf8"));

function hostMatches(host, domain) {
  return host === domain || host.endsWith(`.${domain}`);
}

async function fetchOnce(url) {
  const res = await fetch(url, {
    method: "GET",
    redirect: "follow",
    signal: AbortSignal.timeout(TIMEOUT_MS),
    headers: {
      // Some portals refuse UA-less clients; identify as a plain browser.
      "user-agent": "Mozilla/5.0 (compatible; agri.in link checker)",
      accept: "text/html,*/*",
    },
  });
  return res.status;
}

async function check(entry) {
  const problems = [];
  let parsed;
  try {
    parsed = new URL(entry.url);
  } catch {
    return { entry, status: "-", problems: ["url does not parse"] };
  }
  if (parsed.protocol !== "https:") problems.push("not https");
  if (!hostMatches(parsed.hostname, entry.domain)) {
    problems.push(`host ${parsed.hostname} is not under declared domain ${entry.domain}`);
  }
  if (!ALLOWED_SUFFIXES.some((sfx) => entry.domain === sfx || entry.domain.endsWith(`.${sfx}`))) {
    problems.push(`domain ${entry.domain} not under allowlist (${ALLOWED_SUFFIXES.join(", ")})`);
  }

  let status = "-";
  if (problems.length === 0) {
    try {
      status = await fetchOnce(entry.url);
    } catch {
      // one retry — network flakiness, not a verdict
      try {
        status = await fetchOnce(entry.url);
      } catch (err) {
        problems.push(`unreachable: ${err?.cause?.code ?? err?.name ?? "error"}`);
      }
    }
    if (typeof status === "number" && (status < 200 || status >= 300)) {
      problems.push(`HTTP ${status}`);
    }
  }
  return { entry, status, problems };
}

const results = await Promise.all(entries.map(check));
const failures = results.filter((r) => r.problems.length > 0);

const pad = (s, n) => String(s).padEnd(n);
console.log(pad("KEY", 12) + pad("STATUS", 8) + pad("VERIFIED", 12) + "URL");
for (const { entry, status, problems } of results) {
  const mark = problems.length === 0 ? "OK " : "FAIL ";
  console.log(
    pad(entry.key, 12) + pad(status, 8) + pad(entry.verified_on, 12) + mark + entry.url,
  );
}

if (failures.length > 0) {
  console.error(`\n${failures.length} sarkari link(s) FAILED:`);
  for (const { entry, problems } of failures) {
    console.error(`  ${entry.key}: ${problems.join("; ")}`);
  }
  process.exit(1);
}
console.log(`\nAll ${results.length} sarkari links OK.`);
