import { describe, expect, it } from "vitest";

import { handleLabel } from "./account-identity";

/**
 * AG-U5 P1 — the sidebar's identity card.
 *
 * A5 draws "@murugesan". The catch is that `agri_id` is BOTH the chosen
 * handle and, before anyone chooses one, a machine-generated `AG-XXXXXXX`
 * (identity/agri_id.py). Rendering "@AG-3F7K2Q1" would dress a sequence
 * number up as a name the farmer picked, so the two cases render differently
 * and the server's own `handle_is_fallback` decides which — never a prefix
 * sniff on this side.
 */
describe("handleLabel", () => {
  it("marks a chosen handle with @", () => {
    expect(handleLabel("murugesan", false)).toBe("@murugesan");
  });

  it("leaves a generated AgriID bare", () => {
    expect(handleLabel("AG-3F7K2Q1", true)).toBe("AG-3F7K2Q1");
  });

  it("trusts the server's flag over the shape of the string", () => {
    // Belt and braces: if the backend ever says a value IS chosen, we render
    // it as chosen even when it happens to look generated, and vice versa.
    // The alternative is two copies of the fallback rule drifting apart.
    expect(handleLabel("AG-3F7K2Q1", false)).toBe("@AG-3F7K2Q1");
    expect(handleLabel("murugesan", true)).toBe("murugesan");
  });
});
