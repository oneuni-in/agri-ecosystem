import { describe, expect, it } from "vitest";

import { lowDataCookieString, parseLowDataCookie } from "./low-data-core";

describe("parseLowDataCookie", () => {
  it("explicit cookie wins over the save-data signal", () => {
    expect(parseLowDataCookie("milk_lowdata=1", false)).toBe(true);
    expect(parseLowDataCookie("a=b; milk_lowdata=1; c=d", false)).toBe(true);
    expect(parseLowDataCookie("milk_lowdata=0", true)).toBe(false);
  });

  it("falls back to the browser save-data signal when unset", () => {
    expect(parseLowDataCookie("", true)).toBe(true);
    expect(parseLowDataCookie("a=b", false)).toBe(false);
    expect(parseLowDataCookie("notmilk_lowdata=1", false)).toBe(false);
  });
});

describe("lowDataCookieString", () => {
  it("serializes a year-long samesite cookie", () => {
    expect(lowDataCookieString(true)).toBe(
      "milk_lowdata=1; path=/; max-age=31536000; samesite=lax",
    );
    expect(lowDataCookieString(false)).toBe(
      "milk_lowdata=0; path=/; max-age=31536000; samesite=lax",
    );
  });
});
