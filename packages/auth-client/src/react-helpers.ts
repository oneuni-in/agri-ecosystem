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
