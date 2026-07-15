import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveConfig } from "./config";
import { seal } from "./cookies";
import { recordLogout, resetDenylistForTests } from "./denylist";
import type { SessionPayload } from "./session";

const { cookieStore } = vi.hoisted(() => ({
  cookieStore: { get: vi.fn() },
}));

// getServerUser dynamic-imports next/headers; there's no Next request
// context in vitest, so we stub the module's cookies() with a fake store.
vi.mock("next/headers", () => ({
  cookies: async () => cookieStore,
}));

import { getAccessToken, getServerUser } from "./server";

const cfg = resolveConfig({
  clientId: "web-milk",
  appOrigin: "http://localhost:3000",
  idPublicOrigin: "http://localhost:3003",
  idInternalOrigin: "http://127.0.0.1:8000",
});
const adminCfg = resolveConfig({
  clientId: "web-admin",
  appOrigin: "http://localhost:3004",
  idPublicOrigin: "http://localhost:3003",
  idInternalOrigin: "http://127.0.0.1:8000",
  requiredRoles: ["staff", "super_admin"],
});

async function sessionCookieValue(
  overrides: Partial<SessionPayload> = {},
  cfgFor = cfg,
): Promise<string> {
  const session: SessionPayload = {
    sub: "sub-1",
    agriId: "green_farmer42",
    name: "Asha",
    roles: ["user"],
    accessToken: "at",
    accessExpiresAt: Math.floor(Date.now() / 1000) + 900,
    refreshToken: "rt-1",
    issuedAt: Math.floor(Date.now() / 1000) - 60,
    ...overrides,
  };
  return seal(session as unknown as Record<string, unknown>, cfgFor.sessionSecret, 3600);
}

beforeEach(() => {
  resetDenylistForTests();
  cookieStore.get.mockReset();
});

describe("getServerUser", () => {
  it("valid session -> projection", async () => {
    cookieStore.get.mockReturnValue({ value: await sessionCookieValue() });
    expect(await getServerUser(cfg)).toEqual({
      agriId: "green_farmer42",
      name: "Asha",
      roles: ["user"],
    });
  });

  it("no cookie -> null", async () => {
    cookieStore.get.mockReturnValue(undefined);
    expect(await getServerUser(cfg)).toBeNull();
  });

  it("expired access token -> null (no refresh: RSC cannot write cookies)", async () => {
    cookieStore.get.mockReturnValue({
      value: await sessionCookieValue({ accessExpiresAt: Math.floor(Date.now() / 1000) - 10 }),
    });
    expect(await getServerUser(cfg)).toBeNull();
  });

  it("denylisted sub -> null even with a fresh access token", async () => {
    recordLogout("sub-1", Math.floor(Date.now() / 1000) + 5);
    cookieStore.get.mockReturnValue({ value: await sessionCookieValue() });
    expect(await getServerUser(cfg)).toBeNull();
  });

  it("requiredRoles unmet on the admin app -> null", async () => {
    cookieStore.get.mockReturnValue({ value: await sessionCookieValue({}, adminCfg) });
    expect(await getServerUser(adminCfg)).toBeNull();
  });
});

describe("getAccessToken", () => {
  it("valid session -> raw access token (server-side only)", async () => {
    cookieStore.get.mockReturnValue({ value: await sessionCookieValue() });
    expect(await getAccessToken(cfg)).toBe("at");
  });

  it("no cookie -> null", async () => {
    cookieStore.get.mockReturnValue(undefined);
    expect(await getAccessToken(cfg)).toBeNull();
  });

  it("expired access token -> null (caller heals via /api/auth/me)", async () => {
    cookieStore.get.mockReturnValue({
      value: await sessionCookieValue({ accessExpiresAt: Math.floor(Date.now() / 1000) - 10 }),
    });
    expect(await getAccessToken(cfg)).toBeNull();
  });

  it("requiredRoles unmet -> null (admin gate holds for tokens too)", async () => {
    cookieStore.get.mockReturnValue({ value: await sessionCookieValue({}, adminCfg) });
    expect(await getAccessToken(adminCfg)).toBeNull();
  });

  it("denylisted sub -> null", async () => {
    recordLogout("sub-1", Math.floor(Date.now() / 1000) + 5);
    cookieStore.get.mockReturnValue({ value: await sessionCookieValue() });
    expect(await getAccessToken(cfg)).toBeNull();
  });
});
