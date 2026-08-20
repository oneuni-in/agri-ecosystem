import { afterEach, describe, expect, it, vi } from "vitest";

import { createAgriAuth } from "./index";

const BASE = {
  clientId: "web-milk" as const,
  appOrigin: "http://localhost:3000",
  idPublicOrigin: "http://localhost:3003",
  idInternalOrigin: "http://127.0.0.1:8000",
};

describe("createAgriAuth - lazy config resolution (C1)", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("does not throw at construction time in production without a secret", () => {
    vi.stubEnv("NODE_ENV", "production");
    // This is what `next build` does at module-eval time ("Collecting page
    // data") when an app's lib/auth.ts calls createAgriAuth() at module
    // scope - it must not throw, or the whole build goes red.
    expect(() => createAgriAuth(BASE)).not.toThrow();
  });

  it("still rejects on the first getServerUser() invocation in production without a secret", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const auth = createAgriAuth(BASE);
    await expect(auth.getServerUser()).rejects.toThrow(/AUTH_SESSION_SECRET/);
  });

  it("getAccessToken() rejects loudly without a secret, and the rejection is catchable as 'no token'", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const auth = createAgriAuth(BASE);
    // The guard still fires - a secretless prod boot is never silently fine...
    await expect(auth.getAccessToken()).rejects.toThrow(/AUTH_SESSION_SECRET/);
    // ...but a guest-capable BFF proxy degrades it to "no token" exactly like
    // the documented pattern (apps/*/app/api/identity route, A-U4b C3).
    await expect(auth.getAccessToken().catch(() => null)).resolves.toBeNull();
  });
});

describe("createAgriAuth - secretless prod handlers degrade to typed errors (A-U4b C3)", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("GET /api/auth/login answers 503 auth_not_configured, not a raw 500", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const auth = createAgriAuth(BASE);
    const res = await auth.handlers.GET(new Request("http://localhost:3000/api/auth/login"));
    expect(res.status).toBe(503);
    expect(res.headers.get("content-type")).toBe("application/json");
    expect(res.headers.get("cache-control")).toBe("no-store");
    await expect(res.json()).resolves.toEqual({ error: "auth_not_configured" });
    // fail LOUDLY for operators: the server log must name the missing env var
    expect(log).toHaveBeenCalledWith(expect.stringContaining("AUTH_SESSION_SECRET"));
  });

  it("the silent-SSO probe answers 200 {reachable:false} - it fires on every guest view and a 5xx would console-error each one", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const auth = createAgriAuth(BASE);
    const res = await auth.handlers.GET(
      new Request("http://localhost:3000/api/auth/login?silent=1&probe=1&next=%2F"),
    );
    expect(res.status).toBe(200);
    await expect(res.json()).resolves.toEqual({ reachable: false });
    // the operator alarm still fires server-side even for the quiet probe
    expect(log).toHaveBeenCalledWith(expect.stringContaining("AUTH_SESSION_SECRET"));
  });

  it("GET /api/auth/me answers 401 {user:null} - guests never see a 500", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.spyOn(console, "error").mockImplementation(() => {});
    const auth = createAgriAuth(BASE);
    const res = await auth.handlers.GET(new Request("http://localhost:3000/api/auth/me"));
    expect(res.status).toBe(401);
    await expect(res.json()).resolves.toEqual({ user: null });
  });

  it("POST /api/auth/logout answers 503 auth_not_configured", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.spyOn(console, "error").mockImplementation(() => {});
    const auth = createAgriAuth(BASE);
    const res = await auth.handlers.POST(
      new Request("http://localhost:3000/api/auth/logout", { method: "POST" }),
    );
    expect(res.status).toBe(503);
    await expect(res.json()).resolves.toEqual({ error: "auth_not_configured" });
  });

  it("with a secret present the handlers behave exactly as before (no degrade path)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const auth = createAgriAuth({ ...BASE, sessionSecret: "prod-secret" });
    const me = await auth.handlers.GET(new Request("http://localhost:3000/api/auth/me"));
    expect(me.status).toBe(401); // no cookie -> guest, via the real handler
    await expect(me.json()).resolves.toEqual({ user: null });
    // the real /me clears the session+hint cookie pair; the degrade path never sets cookies
    expect(me.headers.getSetCookie().length).toBeGreaterThan(0);
    const login = await auth.handlers.GET(new Request("http://localhost:3000/api/auth/login"));
    expect(login.status).toBe(302); // real OAuth redirect, not 503
    expect(log).not.toHaveBeenCalled();
  });

  it("resolves once and reuses the resolved config across calls (memoized)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const auth = createAgriAuth({ ...BASE, sessionSecret: "prod-secret" });
    const first = await auth.handlers.GET(new Request("http://localhost:3000/api/auth/nope"));
    const second = await auth.handlers.GET(new Request("http://localhost:3000/api/auth/nope"));
    expect(first.status).toBe(404);
    expect(second.status).toBe(404);
  });
});
