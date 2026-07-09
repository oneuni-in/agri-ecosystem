/**
 * @agri/auth-client — AgriID SSO client.
 *
 * STUB. Sprint 1 (D06–D14) implements OAuth2 Authorization Code + PKCE against
 * AgriID and the OTP mock driver. This file carries the type surface those
 * apps will import, and nothing else: no token storage, no network calls, no
 * crypto. Landing the shape now keeps the Sprint 1 diff additive.
 */
import type { Uuid } from "@agri/types";

/** The three storefronts plus the two internal apps that federate to AgriID. */
export type AgriIdAudience =
  | "web-agri"
  | "web-milk"
  | "web-organic"
  | "web-id"
  | "web-admin";

/** Coarse role set; RBAC detail lands with the identity module in Sprint 1. */
export type AgriRole = "anon" | "user" | "vendor" | "moderator" | "admin";

export interface AgriSession {
  readonly userId: Uuid;
  readonly audience: AgriIdAudience;
  readonly roles: readonly AgriRole[];
  /** Unix seconds. */
  readonly expiresAt: number;
}

export interface AuthClient {
  getSession(): Promise<AgriSession | null>;
  signIn(audience: AgriIdAudience): Promise<void>;
  signOut(): Promise<void>;
}

/** Sprint 1 replaces this with the real PKCE client. */
export function createAuthClient(): AuthClient {
  throw new Error(
    "@agri/auth-client is a D01-A stub; AgriID SSO lands in Sprint 1.",
  );
}
