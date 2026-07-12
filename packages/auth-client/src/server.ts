/**
 * RSC session view. READ-ONLY on purpose: refresh rotation must persist a
 * new cookie, and Next 15 only allows cookie writes in route handlers and
 * server actions - so /api/auth/me owns refresh, and a stale session here is
 * simply null (useAgriUser() heals it client-side).
 */
import type { ResolvedConfig } from "./config";
import { readSession } from "./handlers";
import { projectUser, type AgriUser, type SessionPayload } from "./session";

async function readValidSession(cfg: ResolvedConfig): Promise<SessionPayload | null> {
  const { cookies } = await import("next/headers");
  const store = await cookies();
  const raw = store.get(cfg.sessionCookie)?.value;
  const session = await readSession(cfg, raw ? `${cfg.sessionCookie}=${raw}` : null);
  if (!session) return null;
  if (session.accessExpiresAt <= Math.floor(Date.now() / 1000)) return null;
  if (cfg.requiredRoles.length && !cfg.requiredRoles.some((r) => session.roles.includes(r)))
    return null;
  return session;
}

export async function getServerUser(cfg: ResolvedConfig): Promise<AgriUser | null> {
  const session = await readValidSession(cfg);
  return session ? projectUser(session) : null;
}

/**
 * SERVER-SIDE ONLY: the raw D08 access token for backend calls
 * (Authorization: Bearer). Read-only like getServerUser - an expired token
 * reads as null and the caller retries after GET /api/auth/me rotates the
 * session. Never hand this value to client components.
 */
export async function getAccessToken(cfg: ResolvedConfig): Promise<string | null> {
  const session = await readValidSession(cfg);
  return session?.accessToken ?? null;
}
