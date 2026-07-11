/**
 * BFF route handlers (D10.A/B). Pure (Request) => Response - no next/headers -
 * so the whole OAuth dance is unit-testable. Wire into an app with:
 *   app/api/auth/[...auth]/route.ts -> export const { GET, POST } = auth.handlers
 *
 * The browser only ever receives: a 302, an httpOnly JWE cookie, or a JSON
 * projection. Access and refresh tokens live inside the JWE and in these
 * server-side fetches - nowhere else (non-negotiable 1).
 */
import { decodeJwt } from "jose";

import type { ResolvedConfig } from "./config";
import { clearCookie, readCookie, seal, serializeCookie, unseal } from "./cookies";
import { isRevokedSession, recordLogout } from "./denylist";
import { verifyLogoutToken } from "./jwks";
import { challengeFor, generateState, generateVerifier } from "./pkce";
import { projectUser, type SessionPayload } from "./session";

export const SESSION_COOKIE_MAX_AGE = 30 * 86_400; // refresh-token lifetime
const TX_COOKIE_MAX_AGE = 600;
const CLOCK_SKEW_SECONDS = 30;

interface TxPayload {
  state: string;
  verifier: string;
  next: string;
  silent: boolean;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/";
  return raw;
}

function now(): number {
  return Math.floor(Date.now() / 1000);
}

function json(body: unknown, status: number, cookies: string[] = []): Response {
  const headers = new Headers({ "content-type": "application/json", "cache-control": "no-store" });
  for (const cookie of cookies) headers.append("set-cookie", cookie);
  return new Response(JSON.stringify(body), { status, headers });
}

function redirect(location: string, cookies: string[] = []): Response {
  const headers = new Headers({ location, "cache-control": "no-store" });
  for (const cookie of cookies) headers.append("set-cookie", cookie);
  return new Response(null, { status: 302, headers });
}

/** D09 contract: /token binds the refresh family to the DEVICE, so the
 * browser's identity headers must reach it - not the BFF host's. */
function deviceHeaders(req: Request): Record<string, string> {
  const headers: Record<string, string> = {};
  const ua = req.headers.get("user-agent");
  const platform = req.headers.get("sec-ch-ua-platform");
  if (ua) headers["user-agent"] = ua;
  if (platform) headers["sec-ch-ua-platform"] = platform;
  return headers;
}

export async function exchangeToken(
  cfg: ResolvedConfig,
  form: URLSearchParams,
  req: Request,
): Promise<TokenResponse | null> {
  try {
    const response = await fetch(`${cfg.idInternalOrigin}/token`, {
      method: "POST",
      headers: deviceHeaders(req),
      body: form,
    });
    if (!response.ok) return null;
    const body = (await response.json()) as Partial<TokenResponse>;
    if (!body.access_token || !body.refresh_token || !body.expires_in) return null;
    return body as TokenResponse;
  } catch {
    return null;
  }
}

interface AccessClaims {
  sub: string;
  agri_id: string;
  roles: string[];
  name?: string;
  exp: number;
}

/** decode, not verify: the token arrived over the server-to-server channel
 * straight from the token endpoint - there is no untrusted hop to defend. */
export function sessionFromTokens(tokens: TokenResponse): SessionPayload | null {
  try {
    const claims = decodeJwt(tokens.access_token) as unknown as AccessClaims;
    if (!claims.sub || !claims.agri_id || !Array.isArray(claims.roles)) return null;
    return {
      sub: claims.sub,
      agriId: claims.agri_id,
      name: claims.name ?? null,
      roles: claims.roles,
      accessToken: tokens.access_token,
      accessExpiresAt: claims.exp ?? now() + tokens.expires_in,
      refreshToken: tokens.refresh_token,
      issuedAt: now(),
    };
  } catch {
    return null;
  }
}

function rolesAllowed(cfg: ResolvedConfig, roles: readonly string[]): boolean {
  if (cfg.requiredRoles.length === 0) return true;
  return cfg.requiredRoles.some((role) => roles.includes(role));
}

async function handleLogin(cfg: ResolvedConfig, req: Request): Promise<Response> {
  const url = new URL(req.url);
  const next = safeNext(url.searchParams.get("next"));
  const silent = url.searchParams.get("silent") === "1";
  const verifier = generateVerifier();
  const state = generateState();
  const authorize = new URL("/authorize", cfg.idPublicOrigin);
  authorize.searchParams.set("response_type", "code");
  authorize.searchParams.set("client_id", cfg.clientId);
  authorize.searchParams.set("redirect_uri", `${cfg.appOrigin}/api/auth/callback`);
  authorize.searchParams.set("state", state);
  authorize.searchParams.set("code_challenge", await challengeFor(verifier));
  authorize.searchParams.set("code_challenge_method", "S256");
  if (silent) authorize.searchParams.set("prompt", "none");
  const tx = await seal(
    { state, verifier, next, silent } satisfies TxPayload,
    cfg.sessionSecret,
    TX_COOKIE_MAX_AGE,
  );
  return redirect(authorize.toString(), [
    serializeCookie(cfg.txCookie, tx, { maxAge: TX_COOKIE_MAX_AGE, secure: cfg.secure }),
  ]);
}

async function handleCallback(cfg: ResolvedConfig, req: Request): Promise<Response> {
  const url = new URL(req.url);
  const clearTx = clearCookie(cfg.txCookie, cfg.secure);
  const tx = await unseal<TxPayload>(
    readCookie(req.headers.get("cookie"), cfg.txCookie),
    cfg.sessionSecret,
  );
  const state = url.searchParams.get("state");
  if (!tx || !state || state !== tx.state) {
    // CSRF/state failure: no redirect (nothing user-supplied is trusted here)
    return json({ error: "state_mismatch" }, 400, [clearTx]);
  }
  if (url.searchParams.get("error")) {
    // login_required from a prompt=none probe (D10.B): graceful fallback -
    // land where the user was going, just unauthenticated.
    return redirect(`${cfg.appOrigin}${tx.next}`, [clearTx]);
  }
  const code = url.searchParams.get("code");
  if (!code) return json({ error: "missing_code" }, 400, [clearTx]);
  const form = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: `${cfg.appOrigin}/api/auth/callback`,
    client_id: cfg.clientId,
    code_verifier: tx.verifier,
  });
  const tokens = await exchangeToken(cfg, form, req);
  const session = tokens && sessionFromTokens(tokens);
  if (!session) return json({ error: "code_exchange_failed" }, 502, [clearTx]);
  if (!rolesAllowed(cfg, session.roles)) {
    // non-negotiable 4: the BFF refuses to even create a session
    return json({ error: "forbidden" }, 403, [clearTx]);
  }
  const sealed = await seal(
    session as unknown as Record<string, unknown>,
    cfg.sessionSecret,
    SESSION_COOKIE_MAX_AGE,
  );
  return redirect(`${cfg.appOrigin}${tx.next}`, [
    serializeCookie(cfg.sessionCookie, sealed, {
      maxAge: SESSION_COOKIE_MAX_AGE,
      secure: cfg.secure,
    }),
    clearTx,
  ]);
}

export async function readSession(
  cfg: ResolvedConfig,
  cookieHeader: string | null,
): Promise<SessionPayload | null> {
  const session = await unseal<SessionPayload>(
    readCookie(cookieHeader, cfg.sessionCookie),
    cfg.sessionSecret,
  );
  if (!session) return null;
  if (isRevokedSession(session.sub, session.issuedAt)) return null;
  return session;
}

async function handleMe(cfg: ResolvedConfig, req: Request): Promise<Response> {
  const clear = clearCookie(cfg.sessionCookie, cfg.secure);
  const session = await readSession(cfg, req.headers.get("cookie"));
  if (!session) return json({ user: null }, 401, [clear]);
  if (session.accessExpiresAt - CLOCK_SKEW_SECONDS > now()) {
    if (!rolesAllowed(cfg, session.roles)) return json({ user: null }, 403, [clear]);
    return json({ user: projectUser(session) }, 200);
  }
  // Access token stale: rotate the refresh token (the ~15-minute safety net -
  // a family revoked by logout-everywhere dies HERE even if the back-channel
  // notification never arrived).
  const tokens = await exchangeToken(
    cfg,
    new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: session.refreshToken,
      client_id: cfg.clientId,
    }),
    req,
  );
  const rotated = tokens && sessionFromTokens(tokens);
  if (!rotated) return json({ user: null }, 401, [clear]);
  if (!rolesAllowed(cfg, rotated.roles)) return json({ user: null }, 403, [clear]);
  const resealed = await seal(
    { ...rotated, issuedAt: session.issuedAt } as unknown as Record<string, unknown>,
    cfg.sessionSecret,
    SESSION_COOKIE_MAX_AGE,
  );
  return json({ user: projectUser(rotated) }, 200, [
    serializeCookie(cfg.sessionCookie, resealed, {
      maxAge: SESSION_COOKIE_MAX_AGE,
      secure: cfg.secure,
    }),
  ]);
}

async function handleLogout(cfg: ResolvedConfig, req: Request): Promise<Response> {
  const session = await readSession(cfg, req.headers.get("cookie"));
  if (session) {
    // back-channel to id.agri.in (D10.A): retire our refresh family so the
    // devices manager stops listing this app session. Best-effort.
    try {
      await fetch(`${cfg.idInternalOrigin}/oauth/revoke`, {
        method: "POST",
        body: new URLSearchParams({ client_id: cfg.clientId, token: session.refreshToken }),
      });
    } catch {
      // revocation failure must not trap the user in a logged-in app
    }
  }
  return json({ status: "ok" }, 200, [clearCookie(cfg.sessionCookie, cfg.secure)]);
}

async function handleBackchannelLogout(cfg: ResolvedConfig, req: Request): Promise<Response> {
  let token: unknown = null;
  try {
    token = (await req.formData()).get("logout_token");
  } catch {
    return json({ error: "invalid_request" }, 400);
  }
  if (typeof token !== "string") return json({ error: "invalid_request" }, 400);
  const verified = await verifyLogoutToken(cfg, token);
  if (!verified) return json({ error: "invalid_token" }, 400);
  recordLogout(verified.sub, verified.iat);
  return json({ status: "ok" }, 200);
}

export function createHandlers(cfg: ResolvedConfig): {
  GET: (req: Request) => Promise<Response>;
  POST: (req: Request) => Promise<Response>;
} {
  return {
    GET: async (req) => {
      switch (new URL(req.url).pathname.split("/").at(-1)) {
        case "login":
          return handleLogin(cfg, req);
        case "callback":
          return handleCallback(cfg, req);
        case "me":
          return handleMe(cfg, req);
        default:
          return json({ error: "not_found" }, 404);
      }
    },
    POST: async (req) => {
      switch (new URL(req.url).pathname.split("/").at(-1)) {
        case "logout":
          return handleLogout(cfg, req);
        case "backchannel-logout":
          return handleBackchannelLogout(cfg, req);
        default:
          return json({ error: "not_found" }, 404);
      }
    },
  };
}
