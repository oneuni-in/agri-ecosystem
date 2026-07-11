import { describe, expect, it } from "vitest";

import { currentRelativeUrl, shouldAttemptSilentSso } from "./react-helpers";

describe("shouldAttemptSilentSso", () => {
  it("attempts only on 401 + enabled + no marker", () => {
    expect(shouldAttemptSilentSso(401, true, null)).toBe(true);
    expect(shouldAttemptSilentSso(401, true, "1")).toBe(false);
    expect(shouldAttemptSilentSso(401, false, null)).toBe(false);
    expect(shouldAttemptSilentSso(403, true, null)).toBe(false);
  });
});

describe("currentRelativeUrl", () => {
  it("joins path + search + hash, relative only", () => {
    expect(
      currentRelativeUrl({ pathname: "/shop", search: "?a=1", hash: "#top" } as Location),
    ).toBe("/shop?a=1#top");
  });
});
