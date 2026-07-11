/**
 * In-memory back-channel logout denylist. Single-process per app (the
 * deployment shape through launch); the ~15-minute access-token horizon in
 * /api/auth/me is the safety net for anything this misses (D10.D).
 * sub -> latest logout epoch; a session dies iff issuedAt <= logoutAt.
 */
const TTL_SECONDS = 30 * 86_400; // refresh-token lifetime; nothing older can rotate anyway

type Store = Map<string, number>;

const globalStore = globalThis as { __agriAuthLogoutDenylist?: Store };

function store(): Store {
  return (globalStore.__agriAuthLogoutDenylist ??= new Map());
}

export function recordLogout(sub: string, atEpochSeconds: number): void {
  const map = store();
  const existing = map.get(sub);
  map.set(sub, existing === undefined ? atEpochSeconds : Math.max(existing, atEpochSeconds));
  // Anchored to the incoming event's own clock, not wall-clock Date.now():
  // events arrive close to real time in production, and anchoring here (vs.
  // the system clock) keeps this pure and deterministic under test.
  const horizon = atEpochSeconds - TTL_SECONDS;
  for (const [key, at] of map) if (at < horizon) map.delete(key);
}

export function isRevokedSession(sub: string, issuedAtEpochSeconds: number): boolean {
  const at = store().get(sub);
  return at !== undefined && issuedAtEpochSeconds <= at;
}

export function resetDenylistForTests(): void {
  store().clear();
}
