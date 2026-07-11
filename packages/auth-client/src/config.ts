/**
 * Per-app AgriID SSO config resolution (D10).
 *
 * Cookie names are derived per clientId because every app runs on
 * `localhost` in dev - cookies are port-blind, so a shared name would let
 * one app's session cookie leak into another app's requests.
 */
export interface AgriAuthConfig {
  clientId: "web-agri" | "web-milk" | "web-organic" | "web-admin";
  /** Browser-facing origin of THIS app, e.g. http://localhost:3000. */
  appOrigin: string;
  /** Browser-facing AgriID origin - /authorize (and the login UI) live here.
   * Dev: web-id on http://localhost:3003 (it rewrites /authorize to the API).
   * Prod: https://id.agri.in. */
  idPublicOrigin: string;
  /** Server-to-server API origin - /token, /oauth/revoke, JWKS.
   * Dev: http://127.0.0.1:8000. Prod: https://id.agri.in. */
  idInternalOrigin: string;
  /** Required in production; a fixed dev constant is used otherwise. */
  sessionSecret?: string;
  /** Roles allowed through the BFF; empty = any authenticated user. */
  requiredRoles?: readonly string[];
  /** Backend settings.oauth_issuer - https://id.agri.in in every env. */
  expectedIssuer?: string;
}

export interface ResolvedConfig {
  clientId: AgriAuthConfig["clientId"];
  appOrigin: string;
  idPublicOrigin: string;
  idInternalOrigin: string;
  sessionSecret: string;
  requiredRoles: readonly string[];
  expectedIssuer: string;
  sessionCookie: string;
  txCookie: string;
  secure: boolean;
}

const DEV_SECRET = "agri-dev-session-secret-not-for-prod";

export function resolveConfig(config: AgriAuthConfig): ResolvedConfig {
  let secret = config.sessionSecret;
  if (!secret) {
    if (process.env.NODE_ENV === "production") {
      throw new Error(`${config.clientId}: AUTH_SESSION_SECRET is required in production`);
    }
    secret = DEV_SECRET;
  }
  const sessionCookie = `${config.clientId.replace("web-", "")}_session`;
  return {
    clientId: config.clientId,
    appOrigin: config.appOrigin,
    idPublicOrigin: config.idPublicOrigin,
    idInternalOrigin: config.idInternalOrigin,
    sessionSecret: secret,
    requiredRoles: config.requiredRoles ?? [],
    expectedIssuer: config.expectedIssuer ?? "https://id.agri.in",
    sessionCookie,
    txCookie: `${sessionCookie}_tx`,
    secure: config.appOrigin.startsWith("https:"),
  };
}
