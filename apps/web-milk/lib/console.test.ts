import { describe, expect, it } from "vitest";

import { listingsHref, resolveConsoleUrl } from "./console";

describe("listingsHref", () => {
  it("appends the listings path when there is no trailing slash", () => {
    expect(listingsHref("http://localhost:3002")).toBe("http://localhost:3002/business/listings");
  });

  it("strips a single trailing slash before appending the listings path", () => {
    expect(listingsHref("http://localhost:3002/")).toBe("http://localhost:3002/business/listings");
  });

  it("strips multiple trailing slashes", () => {
    expect(listingsHref("http://localhost:3002//")).toBe("http://localhost:3002/business/listings");
  });
});

describe("resolveConsoleUrl", () => {
  it("falls back to the localhost dev default when unset outside production", () => {
    expect(resolveConsoleUrl(undefined, "development")).toBe("http://localhost:3002");
    expect(resolveConsoleUrl(undefined, "test")).toBe("http://localhost:3002");
    expect(resolveConsoleUrl(undefined, undefined)).toBe("http://localhost:3002");
  });

  it("returns the configured value unchanged when set", () => {
    expect(resolveConsoleUrl("https://agri.in", "production")).toBe("https://agri.in");
    expect(resolveConsoleUrl("https://staging-agri.example", "development")).toBe(
      "https://staging-agri.example",
    );
  });

  it("throws loudly when unset in a production build, rather than defaulting", () => {
    expect(() => resolveConsoleUrl(undefined, "production")).toThrow(/NEXT_PUBLIC_CONSOLE_URL/);
  });
});
