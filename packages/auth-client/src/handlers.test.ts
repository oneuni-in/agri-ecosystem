import { exportJWK, generateKeyPair, SignJWT, type CryptoKey } from "jose";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveConfig } from "./config";
import { seal, unseal } from "./cookies";
import { recordLogout, resetDenylistForTests } from "./denylist";
import { createHandlers, safeNext } from "./handlers";
import { resetJwksCacheForTests } from "./jwks";
import type { SessionPayload } from "./session";

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

function setCookies(res: Response): string[] {
  return res.headers.getSetCookie();
}

/** Unsigned-claims access token - the BFF decodes, it does not verify. */
async function fakeAccessToken(claims: Record<string, unknown>): Promise<string> {
  return new SignJWT({
    sub: "0197c0de-0000-7000-8000-000000000001",
    agri_id: "green_farmer42",
    roles: ["user"],
    ...claims,
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("15m")
    .sign(new TextEncoder().encode("irrelevant"));
}

function stubTokenEndpoint(status: number, body: unknown) {
  const spy = vi.fn<(input: string, init: RequestInit) => Promise<Response>>(
    async () => new Response(JSON.stringify(body), { status }),
  );
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => vi.unstubAllGlobals());

beforeEach(() => {
  resetDenylistForTests();
  resetJwksCacheForTests();
});

describe("safeNext", () => {
  it("allows only single-slash relative paths", () => {
    expect(safeNext("/dash?x=1")).toBe("/dash?x=1");
    expect(safeNext("//evil.example")).toBe("/");
    expect(safeNext("https://evil.example")).toBe("/");
    expect(safeNext(null)).toBe("/");
  });
});

describe("GET /api/auth/login", () => {
  it("302s to /authorize with PKCE and stores the verifier server-side", async () => {
    const { GET } = createHandlers(cfg);
    const res = await GET(new Request("http://localhost:3000/api/auth/login?next=%2Fshop"));
    expect(res.status).toBe(302);
    const location = new URL(res.headers.get("location")!);
    expect(location.origin).toBe("http://localhost:3003");
    expect(location.pathname).toBe("/authorize");
    expect(location.searchParams.get("client_id")).toBe("web-milk");
    expect(location.searchParams.get("redirect_uri")).toBe(
      "http://localhost:3000/api/auth/callback",
    );
    expect(location.searchParams.get("code_challenge_method")).toBe("S256");
    expect(location.searchParams.get("code_challenge")).toBeTruthy();
    expect(location.searchParams.get("prompt")).toBeNull();
    const txCookie = setCookies(res).find((c) => c.startsWith("milk_session_tx="));
    expect(txCookie).toContain("HttpOnly");
    const tx = await unseal<{ state: string; verifier: string; next: string }>(
      txCookie!.split(";")[0]!.split("=").slice(1).join("="),
      cfg.sessionSecret,
    );
    expect(tx?.state).toBe(location.searchParams.get("state"));
    expect(tx?.verifier).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(tx?.next).toBe("/shop");
  });

  it("silent=1 adds prompt=none", async () => {
    const { GET } = createHandlers(cfg);
    const res = await GET(new Request("http://localhost:3000/api/auth/login?silent=1"));
    expect(new URL(res.headers.get("location")!).searchParams.get("prompt")).toBe("none");
  });
});

async function txCookieHeader(overrides: Partial<Record<string, unknown>> = {}): Promise<string> {
  const tx = await seal(
    { state: "st-1", verifier: "v".repeat(43), next: "/shop", silent: false, ...overrides },
    cfg.sessionSecret,
    600,
  );
  return `milk_session_tx=${tx}`;
}

describe("GET /api/auth/callback", () => {
  it("exchanges the code, seals the session, redirects to next", async () => {
    const accessToken = await fakeAccessToken({ name: "Asha" });
    const spy = stubTokenEndpoint(200, {
      access_token: accessToken,
      refresh_token: "refresh-1",
      expires_in: 900,
      token_type: "Bearer",
    });
    const { GET } = createHandlers(cfg);
    const res = await GET(
      new Request("http://localhost:3000/api/auth/callback?code=c1&state=st-1", {
        headers: {
          cookie: await txCookieHeader(),
          "user-agent": "TestBrowser/1.0",
          "sec-ch-ua-platform": '"Windows"',
        },
      }),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("http://localhost:3000/shop");

    // D09 contract: browser UA forwarded to /token for device binding
    const [tokenUrl, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(tokenUrl).toBe("http://127.0.0.1:8000/token");
    const headers = new Headers(init.headers);
    expect(headers.get("user-agent")).toBe("TestBrowser/1.0");
    expect(headers.get("sec-ch-ua-platform")).toBe('"Windows"');
    const form = init.body as URLSearchParams;
    expect(form.get("grant_type")).toBe("authorization_code");
    expect(form.get("code_verifier")).toBe("v".repeat(43));

    const cookies = setCookies(res);
    const sessionCookie = cookies.find((c) => c.startsWith("milk_session="))!;
    expect(sessionCookie).toContain("HttpOnly");
    expect(cookies.some((c) => c.startsWith("milk_session_tx=;") || c.includes("milk_session_tx=; Max-Age=0"))).toBe(true);
    const session = await unseal<SessionPayload>(
      sessionCookie.split(";")[0]!.slice("milk_session=".length),
      cfg.sessionSecret,
    );
    expect(session?.agriId).toBe("green_farmer42");
    expect(session?.name).toBe("Asha");
    expect(session?.refreshToken).toBe("refresh-1");
  });

  it("rejects a state mismatch (CSRF) with 400 and no session", async () => {
    const { GET } = createHandlers(cfg);
    const res = await GET(
      new Request("http://localhost:3000/api/auth/callback?code=c1&state=WRONG", {
        headers: { cookie: await txCookieHeader() },
      }),
    );
    expect(res.status).toBe(400);
    expect(setCookies(res).some((c) => c.startsWith("milk_session=ey"))).toBe(false);
  });

  it("missing tx cookie -> 400", async () => {
    const { GET } = createHandlers(cfg);
    const res = await GET(new Request("http://localhost:3000/api/auth/callback?code=c1&state=st-1"));
    expect(res.status).toBe(400);
  });

  it("error=login_required (silent probe) falls back gracefully to next", async () => {
    const { GET } = createHandlers(cfg);
    const res = await GET(
      new Request("http://localhost:3000/api/auth/callback?error=login_required&state=st-1", {
        headers: { cookie: await txCookieHeader({ silent: true }) },
      }),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("http://localhost:3000/shop");
    expect(setCookies(res).some((c) => c.startsWith("milk_session=ey"))).toBe(false);
  });

  it("interactive flow (silent=false) + error=access_denied -> 400, tx cleared, no session cookie", async () => {
    const { GET } = createHandlers(cfg);
    const res = await GET(
      new Request("http://localhost:3000/api/auth/callback?error=access_denied&state=st-1", {
        headers: { cookie: await txCookieHeader({ silent: false }) },
      }),
    );
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "authorize_failed" });
    const cookies = setCookies(res);
    expect(cookies.some((c) => c.startsWith("milk_session_tx=;") || c.includes("milk_session_tx=; Max-Age=0"))).toBe(
      true,
    );
    expect(cookies.some((c) => c.startsWith("milk_session=ey"))).toBe(false);
  });

  it("silent probe + error=access_denied still falls back gracefully to next", async () => {
    const { GET } = createHandlers(cfg);
    const res = await GET(
      new Request("http://localhost:3000/api/auth/callback?error=access_denied&state=st-1", {
        headers: { cookie: await txCookieHeader({ silent: true }) },
      }),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("http://localhost:3000/shop");
    expect(setCookies(res).some((c) => c.startsWith("milk_session=ey"))).toBe(false);
  });

  it("web-admin gate: non-staff roles -> 403, no session (non-negotiable 4)", async () => {
    stubTokenEndpoint(200, {
      access_token: await fakeAccessToken({ roles: ["user"] }),
      refresh_token: "refresh-1",
      expires_in: 900,
    });
    const { GET } = createHandlers(adminCfg);
    const res = await GET(
      new Request("http://localhost:3004/api/auth/callback?code=c1&state=st-1", {
        headers: {
          cookie: `admin_session_tx=${await seal(
            { state: "st-1", verifier: "v".repeat(43), next: "/", silent: false },
            adminCfg.sessionSecret,
            600,
          )}`,
        },
      }),
    );
    expect(res.status).toBe(403);
    expect(setCookies(res).some((c) => c.startsWith("admin_session=ey"))).toBe(false);
  });

  it("web-admin gate: staff passes", async () => {
    stubTokenEndpoint(200, {
      access_token: await fakeAccessToken({ roles: ["staff", "user"] }),
      refresh_token: "refresh-1",
      expires_in: 900,
    });
    const { GET } = createHandlers(adminCfg);
    const res = await GET(
      new Request("http://localhost:3004/api/auth/callback?code=c1&state=st-1", {
        headers: {
          cookie: `admin_session_tx=${await seal(
            { state: "st-1", verifier: "v".repeat(43), next: "/", silent: false },
            adminCfg.sessionSecret,
            600,
          )}`,
        },
      }),
    );
    expect(res.status).toBe(302);
  });

  it("failed exchange -> 502, tx cleared", async () => {
    stubTokenEndpoint(400, { error: "invalid_grant" });
    const { GET } = createHandlers(cfg);
    const res = await GET(
      new Request("http://localhost:3000/api/auth/callback?code=bad&state=st-1", {
        headers: { cookie: await txCookieHeader() },
      }),
    );
    expect(res.status).toBe(502);
  });

  it("unknown path -> 404", async () => {
    const { GET } = createHandlers(cfg);
    expect((await GET(new Request("http://localhost:3000/api/auth/whatever"))).status).toBe(404);
  });
});

describe("POST /api/auth/*", () => {
  it("unknown path -> 404", async () => {
    const { POST } = createHandlers(cfg);
    const res = await POST(new Request("http://localhost:3000/api/auth/whatever", { method: "POST" }));
    expect(res.status).toBe(404);
  });
});

async function sessionCookieHeader(
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
  return `${cfgFor.sessionCookie}=${await seal(
    session as unknown as Record<string, unknown>,
    cfgFor.sessionSecret,
    3600,
  )}`;
}

describe("GET /api/auth/me", () => {
  it("valid session -> projection only (no sub/tokens in the body)", async () => {
    const { GET } = createHandlers(cfg);
    const res = await GET(
      new Request("http://localhost:3000/api/auth/me", {
        headers: { cookie: await sessionCookieHeader() },
      }),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as { user: unknown };
    expect(body.user).toEqual({
      agriId: "green_farmer42",
      name: "Asha",
      roles: ["user"],
      coinsBalance: 0,
    });
  });

  it("no cookie -> 401", async () => {
    const { GET } = createHandlers(cfg);
    expect((await GET(new Request("http://localhost:3000/api/auth/me"))).status).toBe(401);
  });

  it("expired access token -> refresh grant with forwarded UA, resealed cookie", async () => {
    const accessToken = await fakeAccessToken({});
    const spy = stubTokenEndpoint(200, {
      access_token: accessToken,
      refresh_token: "rt-2",
      expires_in: 900,
    });
    const { GET } = createHandlers(cfg);
    const res = await GET(
      new Request("http://localhost:3000/api/auth/me", {
        headers: {
          cookie: await sessionCookieHeader({
            accessExpiresAt: Math.floor(Date.now() / 1000) - 10,
          }),
          "user-agent": "TestBrowser/1.0",
        },
      }),
    );
    expect(res.status).toBe(200);
    const [, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get("user-agent")).toBe("TestBrowser/1.0");
    expect((init.body as URLSearchParams).get("grant_type")).toBe("refresh_token");
    const resealed = setCookies(res).find((c) => c.startsWith("milk_session=ey"));
    expect(resealed).toBeTruthy();
    const payload = await unseal<SessionPayload>(
      resealed!.split(";")[0]!.slice("milk_session=".length),
      cfg.sessionSecret,
    );
    expect(payload?.refreshToken).toBe("rt-2");
  });

  it("refresh rejected (family revoked) -> 401 + cookie cleared: the TTL safety net", async () => {
    stubTokenEndpoint(400, { error: "invalid_grant" });
    const { GET } = createHandlers(cfg);
    const res = await GET(
      new Request("http://localhost:3000/api/auth/me", {
        headers: {
          cookie: await sessionCookieHeader({
            accessExpiresAt: Math.floor(Date.now() / 1000) - 10,
          }),
        },
      }),
    );
    expect(res.status).toBe(401);
    expect(setCookies(res).some((c) => c.includes("Max-Age=0"))).toBe(true);
  });

  it("denylisted sub -> 401 even with a fresh access token", async () => {
    recordLogout("sub-1", Math.floor(Date.now() / 1000) + 5);
    const { GET } = createHandlers(cfg);
    const res = await GET(
      new Request("http://localhost:3000/api/auth/me", {
        headers: { cookie: await sessionCookieHeader() },
      }),
    );
    expect(res.status).toBe(401);
  });

  it("role gate on the fresh-token branch: role unmet on the admin app -> 403, no session", async () => {
    const { GET } = createHandlers(adminCfg);
    const res = await GET(
      new Request("http://localhost:3004/api/auth/me", {
        headers: { cookie: await sessionCookieHeader({}, adminCfg) },
      }),
    );
    expect(res.status).toBe(403);
    expect(setCookies(res).some((c) => c.startsWith("admin_session=ey"))).toBe(false);
  });

  it("role gate on the refresh branch: rotated roles unmet on the admin app -> 403, no session", async () => {
    stubTokenEndpoint(200, {
      access_token: await fakeAccessToken({ roles: ["user"] }),
      refresh_token: "rt-2",
      expires_in: 900,
    });
    const { GET } = createHandlers(adminCfg);
    const res = await GET(
      new Request("http://localhost:3004/api/auth/me", {
        headers: {
          cookie: await sessionCookieHeader(
            { accessExpiresAt: Math.floor(Date.now() / 1000) - 10 },
            adminCfg,
          ),
        },
      }),
    );
    expect(res.status).toBe(403);
    expect(setCookies(res).some((c) => c.startsWith("admin_session=ey"))).toBe(false);
  });
});

describe("POST /api/auth/logout", () => {
  it("revokes at id.agri.in and clears the cookie", async () => {
    const spy = stubTokenEndpoint(200, { status: "ok" });
    const { POST } = createHandlers(cfg);
    const res = await POST(
      new Request("http://localhost:3000/api/auth/logout", {
        method: "POST",
        headers: { cookie: await sessionCookieHeader() },
      }),
    );
    expect(res.status).toBe(200);
    const [revokeUrl, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(revokeUrl).toBe("http://127.0.0.1:8000/oauth/revoke");
    expect((init.body as URLSearchParams).get("token")).toBe("rt-1");
    expect(setCookies(res).some((c) => c.includes("Max-Age=0"))).toBe(true);
  });

  it("logout without a session is still a clean 200", async () => {
    const { POST } = createHandlers(cfg);
    const res = await POST(
      new Request("http://localhost:3000/api/auth/logout", { method: "POST" }),
    );
    expect(res.status).toBe(200);
  });
});

describe("POST /api/auth/backchannel-logout", () => {
  const LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout";
  let privateKey: CryptoKey;
  let jwksBody: string;

  beforeAll(async () => {
    const pair = await generateKeyPair("RS256");
    privateKey = pair.privateKey;
    const jwk = await exportJWK(pair.publicKey);
    jwksBody = JSON.stringify({ keys: [{ ...jwk, alg: "RS256", use: "sig", kid: "t1" }] });
  });

  function stubJwksFetch() {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () => new Response(jwksBody, { headers: { "content-type": "application/json" } }),
      ),
    );
  }

  async function signLogoutToken(
    overrides: {
      issuer?: string;
      audience?: string;
      events?: Record<string, unknown>;
      subject?: string;
    } = {},
  ): Promise<string> {
    const {
      issuer = "https://id.agri.in",
      audience = "web-milk",
      events = { [LOGOUT_EVENT]: {} },
      subject = "sub-1",
    } = overrides;
    return new SignJWT({ events })
      .setProtectedHeader({ alg: "RS256", kid: "t1" })
      .setIssuer(issuer)
      .setAudience(audience)
      .setSubject(subject)
      .setIssuedAt()
      .setExpirationTime("2m")
      .sign(privateKey);
  }

  it("valid token -> 200 and denylists the sub; a pre-logout session's /me now 401s", async () => {
    stubJwksFetch();
    const { POST, GET } = createHandlers(cfg);
    const res = await POST(
      new Request("http://localhost:3000/api/auth/backchannel-logout", {
        method: "POST",
        body: new URLSearchParams({ logout_token: await signLogoutToken() }),
      }),
    );
    expect(res.status).toBe(200);

    // the cookie's issuedAt (now - 60s) predates the logout event -> dead.
    const meRes = await GET(
      new Request("http://localhost:3000/api/auth/me", {
        headers: { cookie: await sessionCookieHeader() },
      }),
    );
    expect(meRes.status).toBe(401);
  });

  it("invalid signature/audience -> 400, denylist untouched, /me still works", async () => {
    stubJwksFetch();
    const { POST, GET } = createHandlers(cfg);
    const res = await POST(
      new Request("http://localhost:3000/api/auth/backchannel-logout", {
        method: "POST",
        body: new URLSearchParams({
          logout_token: await signLogoutToken({ audience: "web-organic" }),
        }),
      }),
    );
    expect(res.status).toBe(400);

    const meRes = await GET(
      new Request("http://localhost:3000/api/auth/me", {
        headers: { cookie: await sessionCookieHeader() },
      }),
    );
    expect(meRes.status).toBe(200);
  });
});
