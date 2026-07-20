import { describe, expect, it } from "vitest";

import {
  LOC_COOKIE,
  type LocContext,
  locLabel,
  parseLocationResponse,
  parseLocCookie,
  serializeLocCookie,
} from "./location";

const FULL: LocContext = {
  pincode: "641001",
  district: "Coimbatore",
  state: "Tamil Nadu",
  source: "gps",
};

describe("parseLocCookie / serializeLocCookie", () => {
  it("round-trips a full context through serialize -> parse", () => {
    const serialized = serializeLocCookie(FULL);
    const firstPart = serialized.split(";")[0] ?? "";
    const value = firstPart.slice(`${LOC_COOKIE}=`.length);
    expect(parseLocCookie(value)).toEqual(FULL);
  });

  it("round-trips a context with null fields", () => {
    const loc: LocContext = { pincode: null, district: null, state: null, source: "none" };
    const serialized = serializeLocCookie(loc);
    const firstPart = serialized.split(";")[0] ?? "";
    const value = firstPart.slice(`${LOC_COOKIE}=`.length);
    expect(parseLocCookie(value)).toEqual(loc);
  });

  it("returns null for undefined input", () => {
    expect(parseLocCookie(undefined)).toBeNull();
  });

  it("returns null for malformed JSON", () => {
    expect(parseLocCookie("%7Bnot-json")).toBeNull();
    expect(parseLocCookie("not-even-url-encoded-json")).toBeNull();
  });

  it("returns null when required keys are missing", () => {
    expect(parseLocCookie(encodeURIComponent(JSON.stringify({ p: "641001" })))).toBeNull();
    expect(
      parseLocCookie(encodeURIComponent(JSON.stringify({ p: "641001", d: "X", s: "Y" }))),
    ).toBeNull();
  });

  it("returns null when a field has the wrong shape", () => {
    expect(
      parseLocCookie(
        encodeURIComponent(JSON.stringify({ p: 641001, d: "X", s: "Y", src: "gps" })),
      ),
    ).toBeNull();
    expect(
      parseLocCookie(
        encodeURIComponent(JSON.stringify({ p: "641001", d: "X", s: "Y", src: "bogus" })),
      ),
    ).toBeNull();
    expect(parseLocCookie(encodeURIComponent(JSON.stringify(["not", "an", "object"])))).toBeNull();
  });

  it("serialized string is a full Set-Cookie-ready string with SameSite=Lax and never token-shaped", () => {
    const serialized = serializeLocCookie(FULL);
    expect(serialized).toContain("Path=/");
    expect(serialized).toContain("Max-Age=31536000");
    expect(serialized).toContain("SameSite=Lax");
    expect(serialized).not.toContain("HttpOnly");
    expect(serialized).not.toMatch(/eyJ[\w-]{10,}/);
  });

  it("serialized value is URL-encoded JSON starting with %7B (never JWT/JWE-shaped)", () => {
    const serialized = serializeLocCookie(FULL);
    expect(serialized.startsWith(`${LOC_COOKIE}=%7B`)).toBe(true);
  });
});

describe("parseLocationResponse", () => {
  it("accepts a full, well-shaped body", () => {
    expect(
      parseLocationResponse({
        pincode: "641001",
        district: "Coimbatore",
        state: "Tamil Nadu",
        source: "gps",
      }),
    ).toEqual(FULL);
  });

  it("accepts null pincode/district/state fields", () => {
    expect(
      parseLocationResponse({ pincode: null, district: null, state: null, source: "none" }),
    ).toEqual({ pincode: null, district: null, state: null, source: "none" });
  });

  it("rejects a non-object body", () => {
    expect(parseLocationResponse(null)).toBeNull();
    expect(parseLocationResponse(undefined)).toBeNull();
    expect(parseLocationResponse("not an object")).toBeNull();
    expect(parseLocationResponse(["not", "an", "object"])).toBeNull();
  });

  it("rejects a wrong-shaped pincode/district/state field", () => {
    expect(
      parseLocationResponse({ pincode: 641001, district: "X", state: "Y", source: "gps" }),
    ).toBeNull();
    expect(
      parseLocationResponse({ pincode: "641001", district: undefined, state: "Y", source: "gps" }),
    ).toBeNull();
  });

  it("rejects an unknown source value", () => {
    expect(
      parseLocationResponse({ pincode: "641001", district: "X", state: "Y", source: "bogus" }),
    ).toBeNull();
    expect(
      parseLocationResponse({ pincode: "641001", district: "X", state: "Y", source: 1 }),
    ).toBeNull();
  });
});

describe("locLabel", () => {
  it("prefers district + pincode", () => {
    expect(locLabel(FULL)).toBe("Coimbatore · 641001");
  });

  it("falls back to district alone", () => {
    expect(locLabel({ pincode: null, district: "Coimbatore", state: "Tamil Nadu", source: "ip" })).toBe(
      "Coimbatore",
    );
  });

  it("falls back to state alone", () => {
    expect(locLabel({ pincode: null, district: null, state: "Tamil Nadu", source: "ip" })).toBe(
      "Tamil Nadu",
    );
  });

  it("returns null when nothing is known, or when loc itself is null", () => {
    expect(locLabel({ pincode: null, district: null, state: null, source: "none" })).toBeNull();
    expect(locLabel(null)).toBeNull();
  });
});
