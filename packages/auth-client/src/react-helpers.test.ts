import { describe, expect, it } from "vitest";

import { currentRelativeUrl, hasSessionHint, shouldAttemptSilentSso } from "./react-helpers";

describe("shouldAttemptSilentSso", () => {
  it("attempts only on 401 + enabled + no marker", () => {
    expect(shouldAttemptSilentSso(401, true, null)).toBe(true);
    expect(shouldAttemptSilentSso(401, true, "1")).toBe(false);
    expect(shouldAttemptSilentSso(401, false, null)).toBe(false);
    expect(shouldAttemptSilentSso(403, true, null)).toBe(false);
  });
});

describe("hasSessionHint (U4 A1)", () => {
  it("matches the hint cookie the BFF sets, wherever it sits in the header", () => {
    expect(hasSessionHint("milk_session_hint=1")).toBe(true);
    expect(hasSessionHint("NEXT_LOCALE=en; milk_session_hint=1; agri_loc=641001")).toBe(true);
    expect(hasSessionHint("agri_loc=641001; admin_session_hint=1")).toBe(true);
  });

  it("does not match absence, other cookies, or a non-'1' value", () => {
    expect(hasSessionHint("")).toBe(false);
    expect(hasSessionHint("NEXT_LOCALE=en; agri_loc=641001")).toBe(false);
    // the httpOnly session cookie itself is invisible to document.cookie, but
    // a name merely CONTAINING the suffix must not count as a hint
    expect(hasSessionHint("milk_session_hint_backup=1")).toBe(false);
    expect(hasSessionHint("milk_session_hint=0")).toBe(false);
    expect(hasSessionHint("milk_session_hint=12")).toBe(false);
  });
});

describe("currentRelativeUrl", () => {
  it("joins path + search + hash, relative only", () => {
    expect(
      currentRelativeUrl({ pathname: "/shop", search: "?a=1", hash: "#top" } as Location),
    ).toBe("/shop?a=1#top");
  });
});
