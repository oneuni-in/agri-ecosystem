import { describe, expect, it } from "vitest";

import { deviceIcon, siteLabelKey } from "./account-devices";

/**
 * AG-U5 P5 — the read-only device rows.
 *
 * ID-U1 recorded the trap these guard: next-intl's `t()` has no fallback and
 * THROWS on a missing key, so a session belonging to an OAuth client this
 * build has never heard of would take the whole row down with it.
 */
describe("siteLabelKey", () => {
  it("names the sites the catalogue knows", () => {
    expect(siteLabelKey("web-agri")).toBe("sites.web-agri");
    expect(siteLabelKey("web-milk")).toBe("sites.web-milk");
    expect(siteLabelKey("web")).toBe("sites.web");
  });

  it("returns null for a client the catalogue has never heard of", () => {
    // A client_id registered after this build ships must render as itself,
    // not throw. null is the caller's signal to print the raw kind.
    expect(siteLabelKey("web-future-vertical")).toBe(null);
    expect(siteLabelKey("")).toBe(null);
  });
});

describe("deviceIcon", () => {
  it("tells a phone from a computer", () => {
    expect(deviceIcon("Android 14")).toBe("📱");
    expect(deviceIcon("Windows 11")).toBe("💻");
  });

  it("marks an installed app differently from a browser", () => {
    expect(deviceIcon("Installed app · Android")).toBe("📲");
  });

  it("falls back to a computer when the device is unknown", () => {
    expect(deviceIcon(null)).toBe("💻");
    expect(deviceIcon("Weird New OS")).toBe("💻");
  });
});
