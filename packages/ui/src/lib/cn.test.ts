import { describe, expect, it } from "vitest";

import { cn } from "./cn";

describe("cn", () => {
  it("drops falsy inputs", () => {
    expect(cn("a", undefined, null, "c")).toBe("a c");
  });

  it("lets the last conflicting tailwind class win", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
    expect(cn("bg-brand", "bg-tint-milk")).toBe("bg-tint-milk");
  });
});
