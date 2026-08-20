import { describe, expect, it } from "vitest";

import raw from "../data/sarkari.json";
import { pickSarkariText, shouldInterceptClick, type SarkariText } from "./sarkari";

/**
 * A-U4b O2 (AG-A61) — the sarkari detail dialog's pure logic, plus the
 * data-file contract the dialog and the AG-A11 link checker both depend on.
 */

const text: SarkariText = { en: "english", ta: "tamil", hi: "hindi" };

describe("pickSarkariText", () => {
  it("picks the locale's translation", () => {
    expect(pickSarkariText(text, "ta")).toBe("tamil");
    expect(pickSarkariText(text, "hi")).toBe("hindi");
    expect(pickSarkariText(text, "en")).toBe("english");
  });

  it("falls back to English for unknown locales", () => {
    expect(pickSarkariText(text, "fr")).toBe("english");
    expect(pickSarkariText(text, "")).toBe("english");
  });

  it("falls back to English when the translation is blank", () => {
    expect(pickSarkariText({ ...text, ta: "" }, "ta")).toBe("english");
    expect(pickSarkariText({ ...text, hi: "   " }, "hi")).toBe("english");
  });
});

describe("shouldInterceptClick", () => {
  const plain = {
    defaultPrevented: false,
    button: 0,
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
  };

  it("intercepts a plain left-click", () => {
    expect(shouldInterceptClick(plain)).toBe(true);
  });

  it.each([
    ["defaultPrevented", { ...plain, defaultPrevented: true }],
    ["middle click", { ...plain, button: 1 }],
    ["right click", { ...plain, button: 2 }],
    ["cmd-click (new tab, mac)", { ...plain, metaKey: true }],
    ["ctrl-click (new tab)", { ...plain, ctrlKey: true }],
    ["shift-click (new window)", { ...plain, shiftKey: true }],
    ["alt-click (download)", { ...plain, altKey: true }],
  ])("lets the browser handle %s", (_name, event) => {
    expect(shouldInterceptClick(event)).toBe(false);
  });
});

describe("sarkari.json detail contract (E5 + AG-A11 compatibility)", () => {
  const locales = ["en", "ta", "hi"] as const;
  const blocks = ["what", "eligibility", "documents"] as const;

  it.each(raw.entries.map((e) => [e.key, e] as const))(
    "%s keeps the checker fields and carries full detail copy",
    (_key, entry) => {
      // AG-A11 link-checker contract: these field names must stay intact.
      expect(entry.url.startsWith("https://")).toBe(true);
      expect(entry.domain.length).toBeGreaterThan(0);
      expect(entry.verified_on).toMatch(/^\d{4}-\d{2}-\d{2}$/);

      // AG-A61 detail contract: every block, every locale, non-empty.
      for (const block of blocks) {
        for (const locale of locales) {
          expect(entry.detail[block][locale].trim().length).toBeGreaterThan(0);
        }
      }
      // The dialog stamp must be honest: the copy's source IS the official
      // domain the card links to, and the check date is a real ISO date.
      expect(entry.detail.source).toBe(entry.domain);
      expect(entry.detail.last_verified).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    },
  );
});
