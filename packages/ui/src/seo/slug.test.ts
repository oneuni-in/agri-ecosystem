import { describe, expect, it } from "vitest";

import { citySlug } from "./slug";

describe("citySlug", () => {
  it("lowercases and hyphenates district names", () => {
    expect(citySlug("Coimbatore")).toBe("coimbatore");
    expect(citySlug("The Nilgiris")).toBe("the-nilgiris");
  });

  it("strips diacritics and squeezes non-alphanumerics", () => {
    expect(citySlug("Kanniyākumari")).toBe("kanniyakumari");
    expect(citySlug("A  B--C")).toBe("a-b-c");
  });

  it("trims leading/trailing hyphens and handles empty", () => {
    expect(citySlug(" -Chennai- ")).toBe("chennai");
    expect(citySlug("")).toBe("");
  });
});
