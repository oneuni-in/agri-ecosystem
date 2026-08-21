import { readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { LANGUAGES, languageName } from "./languages";

/**
 * The autonym list and the message catalogue must not drift apart.
 *
 * Adding a fourth locale means adding a fourth `<locale>.json`; if the
 * autonym is forgotten, every surface that prints a language name silently
 * falls back to the bare code. This catches that at test time rather than in
 * a screenshot nobody took in that locale.
 */
const MESSAGES_DIR = join(__dirname, "..", "..", "..", "packages", "ui", "src", "i18n", "messages");

describe("LANGUAGES", () => {
  it("covers exactly the locales the catalogue ships", () => {
    const shipped = readdirSync(MESSAGES_DIR)
      .filter((file) => file.endsWith(".json"))
      .map((file) => file.replace(/\.json$/, ""))
      .sort();
    expect(LANGUAGES.map((entry) => entry.code).sort()).toEqual(shipped);
  });

  it("writes each name in its own script, never translated", () => {
    expect(languageName("ta")).toBe("தமிழ்");
    expect(languageName("hi")).toBe("हिंदी");
    expect(languageName("en")).toBe("English");
  });

  it("falls back to the raw code rather than inventing a name", () => {
    // A profile row could carry a language the UI does not know yet. Printing
    // the code is honest; printing "English" would be a guess.
    expect(languageName("kn")).toBe("kn");
    expect(languageName(null)).toBe(null);
  });
});
