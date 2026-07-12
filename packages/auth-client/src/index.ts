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
export { getServerUser } from "./server";

import type { AgriAuthConfig, ResolvedConfig } from "./config";
import { resolveConfig } from "./config";
import { createHandlers } from "./handlers";
import { getServerUser } from "./server";
import type { AgriUser } from "./session";

export interface AgriAuth {
  handlers: ReturnType<typeof createHandlers>;
  /** Read-only session view for RSC - never refreshes (route handlers own
   * cookie writes); a stale session reads as null and useAgriUser() heals it. */
  getServerUser(): Promise<AgriUser | null>;
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
  return {
    handlers: {
      GET: async (req) => getHandlers().GET(req),
      POST: async (req) => getHandlers().POST(req),
    },
    getServerUser: async () => getServerUser(cfg()),
  };
}
