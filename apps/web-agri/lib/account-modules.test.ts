import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { ACCOUNT_MODULES, resolveModuleHref } from "./account-modules";

/**
 * AG-U5 P1 — the /account sidebar registry.
 *
 * These are invariants, not a second copy of the array. Asserting "entry 3 is
 * Saved" would just restate the source and break on every reorder; what is
 * worth guarding is the handful of contracts a later edit could silently
 * violate.
 */

const LOCALES = ["en", "ta", "hi"] as const;
const MESSAGES_DIR = join(__dirname, "..", "..", "..", "packages", "ui", "src", "i18n", "messages");

function navKeys(locale: string): Record<string, unknown> {
  const raw = readFileSync(join(MESSAGES_DIR, `${locale}.json`), "utf8");
  const parsed = JSON.parse(raw) as { ui?: { account?: { nav?: Record<string, unknown> } } };
  return parsed.ui?.account?.nav ?? {};
}

describe("ACCOUNT_MODULES", () => {
  /**
   * The CP0 topology decision, as a test (docs/qa/ag-u5-drift.md §3.1).
   *
   * The owner chose to move /coins, /saved and /notifications under /account,
   * which cost a redirect + link sweep. The way that decision decays is a
   * later edit re-adding a top-level href here because "the module already
   * lives at /saved" — this fails loudly if anyone does.
   */
  it("keeps every internal module inside the /account family", () => {
    const strays = ACCOUNT_MODULES.filter(
      (entry) => !entry.external && entry.href !== "/account" && !entry.href.startsWith("/account/"),
    );
    expect(strays).toEqual([]);
  });

  it("routes profile edits off this app and onto AgriID", () => {
    const external = ACCOUNT_MODULES.filter((entry) => entry.external);
    // Identity is CONSUMED, never rebuilt (AG-U5 out-of-bounds). Exactly one
    // entry leaves the app, and it is the profile one.
    expect(external.map((entry) => entry.id)).toEqual(["profile"]);
  });

  it("groups the settings entries together at the end", () => {
    // The sidebar renders main entries, then a "Settings" label, then the
    // rest. An interleaved registry would render a settings entry above the
    // label, which reads as a main entry.
    const flags = ACCOUNT_MODULES.map((entry) => entry.group === "settings");
    const firstSettings = flags.indexOf(true);
    expect(firstSettings).toBeGreaterThan(0);
    expect(flags.slice(firstSettings).every(Boolean)).toBe(true);
  });

  it("gives every module a unique id", () => {
    const ids = ACCOUNT_MODULES.map((entry) => entry.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  /**
   * The shared-catalog trap: ui.* lives in packages/ui and is read by agri,
   * milk, organic and id alike. A module added here without its three strings
   * renders a raw key like "nav.alerts" in the sidebar — visible, and only in
   * the locale nobody checked.
   */
  it.each(LOCALES)("has a %s label for every module", (locale) => {
    const keys = navKeys(locale);
    const missing = ACCOUNT_MODULES.filter((entry) => typeof keys[entry.id] !== "string");
    expect(missing.map((entry) => entry.id)).toEqual([]);
  });
});

describe("resolveModuleHref", () => {
  const idOrigin = "https://id.agri.in";

  it("leaves an internal path alone", () => {
    const saved = ACCOUNT_MODULES.find((entry) => entry.id === "saved");
    expect(saved && resolveModuleHref(saved, idOrigin)).toBe("/account/saved");
  });

  it("hangs an external path off the AgriID origin", () => {
    const profile = ACCOUNT_MODULES.find((entry) => entry.id === "profile");
    expect(profile && resolveModuleHref(profile, idOrigin)).toBe("https://id.agri.in/account");
  });

  it("does not double the slash when the origin carries a trailing one", () => {
    const profile = ACCOUNT_MODULES.find((entry) => entry.id === "profile");
    expect(profile && resolveModuleHref(profile, "https://id.agri.in/")).toBe(
      "https://id.agri.in/account",
    );
  });
});
