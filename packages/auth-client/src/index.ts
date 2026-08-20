/**
 * @agri/auth-client - AgriID SSO via the BFF pattern (D10).
 *
 * Each app runs the OAuth2 code + PKCE dance inside its own Next route
 * handlers; the browser holds ONLY that app's httpOnly JWE session cookie.
 * See README.md for wiring and the prod domain map.
 */
export type { AgriAuthConfig } from "./config";
export { resolveConfig } from "./config";
export type { AgriUser } from "./session";
export { createHandlers, readSession, safeNext } from "./handlers";
export { getServerUser, getAccessToken } from "./server";

import type { AgriAuthConfig, ResolvedConfig } from "./config";
import { resolveConfig } from "./config";
import { createHandlers } from "./handlers";
import { getAccessToken, getServerUser } from "./server";
import type { AgriUser } from "./session";

export interface AgriAuth {
  handlers: ReturnType<typeof createHandlers>;
  /** Read-only session view for RSC - never refreshes (route handlers own
   * cookie writes); a stale session reads as null and useAgriUser() heals it.
   * THROWS if the auth config cannot resolve (secretless prod boot). */
  getServerUser(): Promise<AgriUser | null>;
  /** Server-side only: bearer token for backend API calls. Stale -> null;
   * call GET /api/auth/me to rotate, then retry once.
   * THROWS if the auth config cannot resolve (secretless prod boot) - a
   * guest-capable BFF proxy must catch that and treat it as "no token"
   * (`.catch(() => null)`), never surface it as a 500 on a public read. */
  getAccessToken(): Promise<string | null>;
}

/**
 * Typed degrade for an UNCONFIGURED auth deployment (A-U4b C3).
 *
 * The prod-secret guard fires lazily on the first request (see the note in
 * createAgriAuth), which used to surface as a raw 500 + stack in the guest's
 * browser console for /api/auth/login and /api/auth/me on a secretless prod
 * boot. The guard's purpose - a misconfigured prod deploy fails LOUDLY for
 * operators - is kept by the server-side error log naming the missing env
 * var; the browser instead gets a deliberate typed answer:
 *   - GET /me -> 401 {user:null}: to the client, "auth capability absent"
 *     and "no session" are the same guest state (never 500 the guest page -
 *     the milk §2b lesson).
 *   - GET /login?silent=1&probe=1 -> 200 {reachable:false}: the probe's own
 *     contract is "would a silent redirect get anywhere?", and with no auth
 *     config the answer is simply no. It is a background fetch useAgriUser
 *     fires on EVERY guest page view, and browsers log any 4xx/5xx resource
 *     as a console error - answering it 503 traded three 500s for one 503
 *     and still failed AG-A1's clean-console bar (measured on the first
 *     secretless prod boot, 2026-08-20). The operator alarm is not lost:
 *     the server-side error line below still fires per request.
 *   - every other auth route -> 503 {error:"auth_not_configured"}: the auth
 *     capability itself is down until an operator intervenes. That is a
 *     server-side, deployment-scoped condition - 503 Service Unavailable -
 *     not a client error (4xx would blame the caller) and not a missing
 *     route (404 would lie to monitoring about what is wrong). An
 *     INTERACTIVE login attempt deliberately stays loud.
 */
function authNotConfigured(req: Request, error: unknown): Response {
  console.error(
    `[auth-client] auth handlers hit before config could resolve - is AUTH_SESSION_SECRET set? (${String(error)})`,
  );
  const url = new URL(req.url);
  const probe =
    url.searchParams.get("silent") === "1" && url.searchParams.get("probe") === "1";
  const me = url.pathname.split("/").at(-1) === "me";
  const body = probe ? { reachable: false } : me ? { user: null } : { error: "auth_not_configured" };
  return new Response(JSON.stringify(body), {
    status: probe ? 200 : me ? 401 : 503,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export function createAgriAuth(config: AgriAuthConfig): AgriAuth {
  // Config resolution (and its prod-secret guard) is LAZY + MEMOIZED: apps
  // call createAgriAuth() at module scope in lib/auth.ts, and `next build`
  // evaluates route modules during "Collecting page data" under
  // NODE_ENV=production - resolving eagerly here would fail every prod
  // build for any app missing AUTH_SESSION_SECRET at build time, even
  // though it's set in the real runtime environment. Resolving on first
  // request instead means the guard still fires - just at the first
  // request, not at import time - so a genuinely missing secret still
  // fails loudly in production, only later.
  let resolved: ResolvedConfig | undefined;
  const cfg = () => (resolved ??= resolveConfig(config));
  let handlers: ReturnType<typeof createHandlers> | undefined;
  const getHandlers = () => (handlers ??= createHandlers(cfg()));
  // Only cfg()'s synchronous resolution failure is caught here - anything a
  // resolved handler throws later is a genuine bug and should stay a 500.
  const dispatch = async (
    req: Request,
    method: "GET" | "POST",
  ): Promise<Response> => {
    let h: ReturnType<typeof createHandlers>;
    try {
      h = getHandlers();
    } catch (error) {
      return authNotConfigured(req, error);
    }
    return h[method](req);
  };
  return {
    handlers: {
      GET: async (req) => dispatch(req, "GET"),
      POST: async (req) => dispatch(req, "POST"),
    },
    getServerUser: async () => getServerUser(cfg()),
    getAccessToken: async () => getAccessToken(cfg()),
  };
}
