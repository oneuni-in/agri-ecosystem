/** What the browser is allowed to know (non-negotiable 3): no internal UUID,
 * no phone, no tokens. Built EXPLICITLY field-by-field - never by spreading
 * the session payload. */
export interface AgriUser {
  agriId: string;
  name: string | null;
  roles: readonly string[];
  /** AgriCoins land in a later spec; headers render this today. */
  coinsBalance: number;
}

/** Server-side only - lives inside the JWE session cookie. */
export interface SessionPayload {
  /** Internal user UUID (token `sub`) - denylist key, NEVER projected. */
  sub: string;
  agriId: string;
  name: string | null;
  roles: string[];
  accessToken: string;
  /** Unix seconds. */
  accessExpiresAt: number;
  refreshToken: string;
  /** Unix seconds; back-channel logout kills sessions issued before it. */
  issuedAt: number;
}

export function projectUser(session: SessionPayload): AgriUser {
  return {
    agriId: session.agriId,
    name: session.name,
    roles: [...session.roles],
    coinsBalance: 0,
  };
}
