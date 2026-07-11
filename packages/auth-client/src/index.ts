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

import type { AgriAuthConfig } from "./config";
import { resolveConfig } from "./config";
import { createHandlers } from "./handlers";
import type { AgriUser } from "./session";

export interface AgriAuth {
  handlers: ReturnType<typeof createHandlers>;
  /** Read-only session view for RSC - never refreshes (route handlers own
   * cookie writes); a stale session reads as null and useAgriUser() heals it. */
  getServerUser(): Promise<AgriUser | null>;
}

export function createAgriAuth(config: AgriAuthConfig): AgriAuth {
  const cfg = resolveConfig(config);
  return {
    handlers: createHandlers(cfg),
    // Task 9 replaces this with ./server (RSC cookie-store read + rotation).
    getServerUser: async () => null,
  };
}
