import { describe, expect, it } from "vitest";

import { clampScore } from "./profile-nudge";

describe("clampScore", () => {
  it("clamps into 0..100 and rounds", () => {
    expect(clampScore(-5)).toBe(0);
    expect(clampScore(0)).toBe(0);
    expect(clampScore(59.6)).toBe(60);
    expect(clampScore(100)).toBe(100);
    expect(clampScore(140)).toBe(100);
  });
});
