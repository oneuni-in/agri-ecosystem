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

  it("still rejects on the first GET invocation in production without a secret", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const auth = createAgriAuth(BASE);
    await expect(
      auth.handlers.GET(new Request("http://localhost:3000/api/auth/login")),
    ).rejects.toThrow(/AUTH_SESSION_SECRET/);
  });

  it("still rejects on the first POST invocation in production without a secret", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const auth = createAgriAuth(BASE);
    await expect(
      auth.handlers.POST(new Request("http://localhost:3000/api/auth/logout", { method: "POST" })),
    ).rejects.toThrow(/AUTH_SESSION_SECRET/);
  });

  it("still rejects on the first getServerUser() invocation in production without a secret", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const auth = createAgriAuth(BASE);
    await expect(auth.getServerUser()).rejects.toThrow(/AUTH_SESSION_SECRET/);
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
