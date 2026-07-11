import { describe, expect, it } from "vitest";

import { challengeFor, generateState, generateVerifier } from "./pkce";

describe("pkce", () => {
  it("verifier is 43-char base64url (32 random bytes)", () => {
    const v = generateVerifier();
    expect(v).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(generateVerifier()).not.toBe(v);
  });

  it("challenge is the RFC 7636 S256 of the verifier", async () => {
    // RFC 7636 appendix B reference vector
    expect(await challengeFor("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")).toBe(
      "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    );
  });

  it("state is url-safe and unique", () => {
    const s = generateState();
    expect(s).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(generateState()).not.toBe(s);
  });
});
