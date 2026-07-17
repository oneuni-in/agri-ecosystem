import { describe, expect, it } from "vitest";

import { buildMetadata, canonicalUrl, shouldNoIndex } from "./meta";

describe("canonicalUrl", () => {
  it("joins base and path with exactly one slash", () => {
    expect(canonicalUrl("https://x.in/", "/a/b")).toBe("https://x.in/a/b");
    expect(canonicalUrl("https://x.in", "a/b")).toBe("https://x.in/a/b");
  });

  it("strips query, hash and trailing slashes", () => {
    expect(canonicalUrl("https://x.in", "/a/?page=2#top")).toBe("https://x.in/a");
    expect(canonicalUrl("https://x.in", "/")).toBe("https://x.in");
  });
});

describe("shouldNoIndex", () => {
  it("noindexes thin pages until the minimum is met", () => {
    expect(shouldNoIndex(0)).toBe(true);
    expect(shouldNoIndex(1)).toBe(false);
    expect(shouldNoIndex(4, 5)).toBe(true);
  });
});

describe("buildMetadata", () => {
  it("sets canonical + OG url from one input", () => {
    const meta = buildMetadata({
      title: "T",
      description: "D",
      canonical: "https://x.in/a",
    });
    expect(meta.alternates?.canonical).toBe("https://x.in/a");
    expect(meta.openGraph?.url).toBe("https://x.in/a");
    expect(meta.robots).toBeUndefined();
  });

  it("adds robots noindex only when asked", () => {
    const meta = buildMetadata({
      title: "T",
      description: "D",
      canonical: "https://x.in/a",
      noIndex: true,
    });
    expect(meta.robots).toEqual({ index: false, follow: true });
  });

  it("omits description when not given, while title/canonical/openGraph still work", () => {
    const meta = buildMetadata({
      title: "T",
      canonical: "https://x.in/a",
    });
    expect(meta.description).toBeUndefined();
    expect("description" in meta).toBe(false);
    expect(meta.openGraph?.description).toBeUndefined();
    expect(meta.openGraph && "description" in meta.openGraph).toBe(false);
    expect(meta.title).toBe("T");
    expect(meta.alternates?.canonical).toBe("https://x.in/a");
    expect(meta.openGraph?.url).toBe("https://x.in/a");
  });
});
