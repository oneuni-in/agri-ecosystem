/**
 * Verifies back-channel logout tokens (D10.D) against the AgriID JWKS.
 * The remote key set is cached per origin - jose handles refetch on
 * unknown-kid, matching the backend's rotation-overlap runbook.
 */
import { createRemoteJWKSet, jwtVerify } from "jose";

import type { ResolvedConfig } from "./config";

const LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout";

type JwksResolver = ReturnType<typeof createRemoteJWKSet>;
const jwksCache = new Map<string, JwksResolver>();

function jwksFor(origin: string): JwksResolver {
  let resolver = jwksCache.get(origin);
  if (!resolver) {
    resolver = createRemoteJWKSet(new URL("/.well-known/jwks.json", origin));
    jwksCache.set(origin, resolver);
  }
  return resolver;
}

export async function verifyLogoutToken(
  cfg: ResolvedConfig,
  token: string,
): Promise<{ sub: string; iat: number } | null> {
  try {
    const { payload } = await jwtVerify(token, jwksFor(cfg.idInternalOrigin), {
      issuer: cfg.expectedIssuer,
      audience: cfg.clientId,
      algorithms: ["RS256"],
    });
    const events = payload.events as Record<string, unknown> | undefined;
    if (!events || !(LOGOUT_EVENT in events)) return null;
    if (typeof payload.sub !== "string" || typeof payload.iat !== "number") return null;
    return { sub: payload.sub, iat: payload.iat };
  } catch {
    return null;
  }
}

export function resetJwksCacheForTests(): void {
  jwksCache.clear();
}
