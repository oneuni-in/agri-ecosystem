import { describe, expect, it } from "vitest";

import { clearCookie, readCookie, seal, serializeCookie, unseal } from "./cookies";

const SECRET = "test-secret";

describe("seal/unseal", () => {
  it("round-trips a payload", async () => {
    const token = await seal({ hello: "world" }, SECRET, 60);
    expect(await unseal<{ hello: string }>(token, SECRET)).toMatchObject({ hello: "world" });
  });

  it("returns null on tamper, wrong key, expiry, or garbage", async () => {
    const token = await seal({ a: 1 }, SECRET, 60);
    expect(await unseal(`${token}x`, SECRET)).toBeNull();
    expect(await unseal(token, "other-secret")).toBeNull();
    expect(await unseal("not-a-jwe", SECRET)).toBeNull();
    const expired = await seal({ a: 1 }, SECRET, -10);
    expect(await unseal(expired, SECRET)).toBeNull();
  });
});

describe("cookie helpers", () => {
  it("serializes httpOnly + SameSite=Lax always; Secure only when asked", () => {
    const insecure = serializeCookie("milk_session", "v", { maxAge: 60, secure: false });
    expect(insecure).toContain("HttpOnly");
    expect(insecure).toContain("SameSite=Lax");
    expect(insecure).toContain("Path=/");
    expect(insecure).not.toContain("Secure");
    expect(serializeCookie("s", "v", { maxAge: 60, secure: true })).toContain("Secure");
  });

  it("clearCookie expires immediately", () => {
    expect(clearCookie("milk_session", false)).toContain("Max-Age=0");
  });

  it("readCookie finds a cookie in a header", () => {
    expect(readCookie("a=1; milk_session=abc; b=2", "milk_session")).toBe("abc");
    expect(readCookie(null, "milk_session")).toBeNull();
    expect(readCookie("a=1", "milk_session")).toBeNull();
  });
});
