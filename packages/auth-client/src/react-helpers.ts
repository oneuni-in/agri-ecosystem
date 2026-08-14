/** Pure pieces of useAgriUser, split out so the policy is vitest-covered
 * without a DOM harness. */
export const SSO_MARKER = "agri_sso_attempted"; // boolean marker - never a token

export function shouldAttemptSilentSso(
  status: number,
  enabled: boolean,
  marker: string | null,
): boolean {
  return enabled && status === 401 && marker === null;
}

export function currentRelativeUrl(location: Pick<Location, "pathname" | "search" | "hash">): string {
  return `${location.pathname}${location.search}${location.hash}`;
}

/**
 * Does `document.cookie` carry a session-hint cookie (U4 A1)? The hint is the
 * browser-readable companion the BFF sets beside its httpOnly session cookie
 * (`<app>_session_hint=1`, see config.ts) — matched by SHAPE, not by exact
 * name, so this module needs no per-app config. On localhost every app shares
 * one port-blind cookie jar, so another app's hint can match here; that costs
 * one dev-only /api/auth/me 401 (today's behavior on every load) and prod
 * domains are distinct, so the match is exact where it matters.
 */
export function hasSessionHint(cookieHeader: string): boolean {
  return /(?:^|;\s*)[a-z]+_session_hint=1(?:;|$)/.test(cookieHeader);
}
