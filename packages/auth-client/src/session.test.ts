import { describe, expect, it } from "vitest";

import { projectUser, type SessionPayload } from "./session";

const FULL: SessionPayload = {
  sub: "0197c0de-0000-7000-8000-000000000001",
  agriId: "green_farmer42",
  name: "Asha",
  roles: ["user"],
  accessToken: "eyJ.access.token",
  accessExpiresAt: 2_000_000_000,
  refreshToken: "raw-refresh",
  issuedAt: 1_900_000_000,
};

describe("projectUser (non-negotiable 3)", () => {
  it("exposes exactly agriId, name, roles - nothing else", () => {
    const user = projectUser(FULL);
    expect(Object.keys(user).sort()).toEqual(["agriId", "name", "roles"]);
    expect(JSON.stringify(user)).not.toContain(FULL.sub);
    expect(JSON.stringify(user)).not.toContain(FULL.accessToken);
    expect(JSON.stringify(user)).not.toContain(FULL.refreshToken);
  });
});
