import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveConfig } from "./config";

const BASE = {
  clientId: "web-milk" as const,
  appOrigin: "http://localhost:3000",
  idPublicOrigin: "http://localhost:3003",
  idInternalOrigin: "http://127.0.0.1:8000",
};

describe("resolveConfig", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("derives per-app cookie names (localhost is port-blind)", () => {
    const cfg = resolveConfig(BASE);
    expect(cfg.sessionCookie).toBe("milk_session");
    expect(cfg.txCookie).toBe("milk_session_tx");
  });

  it("secure tracks the app origin protocol", () => {
    expect(resolveConfig(BASE).secure).toBe(false);
    expect(resolveConfig({ ...BASE, appOrigin: "https://milk.in" }).secure).toBe(true);
  });

  it("falls back to a dev secret outside production, throws in production", () => {
    expect(resolveConfig(BASE).sessionSecret).toBeTruthy();
    vi.stubEnv("NODE_ENV", "production");
    expect(() => resolveConfig(BASE)).toThrow(/AUTH_SESSION_SECRET/);
    expect(resolveConfig({ ...BASE, sessionSecret: "prod-secret" }).sessionSecret).toBe(
      "prod-secret",
    );
  });

  it("defaults issuer and roles", () => {
    const cfg = resolveConfig(BASE);
    expect(cfg.expectedIssuer).toBe("https://id.agri.in");
    expect(cfg.requiredRoles).toEqual([]);
  });
});
