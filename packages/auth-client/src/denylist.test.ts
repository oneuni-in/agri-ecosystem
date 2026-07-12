import { beforeEach, describe, expect, it } from "vitest";

import { isRevokedSession, recordLogout, resetDenylistForTests } from "./denylist";

describe("back-channel logout denylist", () => {
  beforeEach(resetDenylistForTests);

  it("kills sessions issued before the logout, spares later logins", () => {
    recordLogout("sub-1", 1_000);
    expect(isRevokedSession("sub-1", 999)).toBe(true);
    expect(isRevokedSession("sub-1", 1_000)).toBe(true);
    expect(isRevokedSession("sub-1", 1_001)).toBe(false);
    expect(isRevokedSession("sub-2", 999)).toBe(false);
  });

  it("keeps the latest logout time", () => {
    recordLogout("sub-1", 1_000);
    recordLogout("sub-1", 500); // out-of-order delivery must not resurrect
    expect(isRevokedSession("sub-1", 700)).toBe(true);
  });

  it("does not prune other subs when processing a skewed future timestamp", () => {
    const now = Math.floor(Date.now() / 1000);

    // Record sub-b logout at a recent time (within TTL window)
    recordLogout("sub-b", now - 100);
    expect(isRevokedSession("sub-b", now - 101)).toBe(true);

    // Record sub-a logout at far-future timestamp (10 years from now)
    const farFuture = now + 10 * 365 * 86400;
    recordLogout("sub-a", farFuture);

    // sub-b's entry should still be there, not pruned by the far-future horizon
    expect(isRevokedSession("sub-b", now - 101)).toBe(true);
  });
});
