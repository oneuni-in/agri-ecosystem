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
});
