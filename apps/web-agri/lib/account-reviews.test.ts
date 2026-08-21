import { describe, expect, it } from "vitest";

import { pickBody, statusTone } from "./account-reviews";

/**
 * AG-U5 P4 — how a review renders to the person who wrote it.
 */
describe("statusTone", () => {
  it("maps each moderation status to its own label", () => {
    expect(statusTone("approved").key).toBe("published");
    expect(statusTone("pending").key).toBe("pending");
    expect(statusTone("rejected").key).toBe("rejected");
  });

  it("treats an unknown status as still-in-moderation, never as published", () => {
    // If the enum ever grows a value this build has not seen, the safe
    // reading is "not live yet". Claiming something is published when it may
    // not be is the one error with a consequence.
    expect(statusTone("quarantined").key).toBe("pending");
  });
});

describe("pickBody", () => {
  it("prefers the reader's own language", () => {
    expect(pickBody({ en: "Good service", ta: "நல்ல சேவை" }, "ta")).toBe("நல்ல சேவை");
  });

  it("falls back to any language rather than showing nothing", () => {
    // The author wrote these words. Hiding them because the UI is in Hindi
    // today would be worse than showing them in the language they were
    // written in.
    expect(pickBody({ ta: "நல்ல சேவை" }, "hi")).toBe("நல்ல சேவை");
  });

  it("returns null for a review with no body at all", () => {
    // A rating with no text is legal — the body column is nullable.
    expect(pickBody(null, "en")).toBe(null);
    expect(pickBody({}, "en")).toBe(null);
  });
});
