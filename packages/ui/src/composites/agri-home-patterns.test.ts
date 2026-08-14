import { describe, expect, it } from "vitest";

import { sparkPoints } from "./agri-home-patterns";
import { formatCount } from "./count-up";

describe("sparkPoints", () => {
  it("spans the full 110×26 reference space, y inverted and padded", () => {
    // min lands at height-pad (23), max at pad (3), first x=0, last x=110.
    expect(sparkPoints([10, 20])).toBe("0,23 110,3");
  });

  it("spaces intermediate points evenly", () => {
    const pts = sparkPoints([1, 2, 3]).split(" ").map((p) => p.split(",").map(Number));
    expect(pts.map(([x]) => x)).toEqual([0, 55, 110]);
    expect(pts[1]?.[1]).toBe(13); // midpoint of the padded band
  });

  it("draws a flat series as the centre line, not a divide-by-zero", () => {
    expect(sparkPoints([23, 23, 23])).toBe("0,13 55,13 110,13");
  });

  it("handles empty and single-value series", () => {
    expect(sparkPoints([])).toBe("");
    expect(sparkPoints([42])).toBe("0,13");
  });
});

describe("formatCount", () => {
  it("keeps small numbers bare (unit suffix lives in the label)", () => {
    expect(formatCount(36)).toBe("36");
    expect(formatCount(96)).toBe("96");
  });

  it("gives thousands Indian grouping and a trailing plus", () => {
    expect(formatCount(1450)).toBe("1,450+");
    expect(formatCount(230000)).toBe("2,30,000+");
  });
});
