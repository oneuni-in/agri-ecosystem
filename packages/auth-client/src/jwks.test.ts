import { exportJWK, generateKeyPair, type CryptoKey, SignJWT } from "jose";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import type { ResolvedConfig } from "./config";
import { resetJwksCacheForTests, verifyLogoutToken } from "./jwks";

const LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout";

let privateKey: CryptoKey;
let jwksBody: string;

const CFG = {
  clientId: "web-milk",
  idInternalOrigin: "http://127.0.0.1:8000",
  expectedIssuer: "https://id.agri.in",
} as ResolvedConfig;

beforeAll(async () => {
  const pair = await generateKeyPair("RS256");
  privateKey = pair.privateKey;
  const jwk = await exportJWK(pair.publicKey);
  jwksBody = JSON.stringify({ keys: [{ ...jwk, alg: "RS256", use: "sig", kid: "t1" }] });
});

function stubJwksFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(jwksBody, { headers: { "content-type": "application/json" } })),
  );
}

async function sign(overrides: {
  issuer?: string;
  audience?: string;
  events?: Record<string, unknown>;
}): Promise<string> {
  const { issuer = "https://id.agri.in", audience = "web-milk", events = { [LOGOUT_EVENT]: {} } } =
    overrides;
  return new SignJWT({ events })
    .setProtectedHeader({ alg: "RS256", kid: "t1" })
    .setIssuer(issuer)
    .setAudience(audience)
    .setSubject("sub-123")
    .setIssuedAt()
    .setExpirationTime("2m")
    .sign(privateKey);
}

describe("verifyLogoutToken", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    resetJwksCacheForTests();
  });

  it("accepts a well-formed logout token", async () => {
    stubJwksFetch();
    const result = await verifyLogoutToken(CFG, await sign({}));
    expect(result?.sub).toBe("sub-123");
    expect(typeof result?.iat).toBe("number");
  });

  it("rejects wrong audience, wrong issuer, missing events", async () => {
    stubJwksFetch();
    expect(await verifyLogoutToken(CFG, await sign({ audience: "web-organic" }))).toBeNull();
    expect(await verifyLogoutToken(CFG, await sign({ issuer: "https://evil.example" }))).toBeNull();
    expect(await verifyLogoutToken(CFG, await sign({ events: {} }))).toBeNull();
    expect(await verifyLogoutToken(CFG, "garbage")).toBeNull();
  });
});
