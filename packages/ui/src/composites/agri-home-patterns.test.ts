import { describe, expect, it } from "vitest";

import { sparkPoints, sparkSegments } from "./agri-home-patterns";
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

describe("sparkSegments", () => {
  it("draws contiguous days as ONE segment, spaced exactly like sparkPoints", () => {
    const days = ["2026-08-14", "2026-08-15", "2026-08-16"];
    expect(sparkSegments([1, 2, 3], days)).toEqual([sparkPoints([1, 2, 3])]);
  });

  it("breaks the line over a hole (18–19 Aug 2026 never gets data)", () => {
    // 17 Aug → 20 Aug is a 3-day jump: two segments, no line through it.
    const days = ["2026-08-16", "2026-08-17", "2026-08-20"];
    expect(sparkSegments([10, 20, 30], days)).toEqual(["0,23 27.5,13", "110,3"]);
  });

  it("positions x proportionally to the actual dates, not the index", () => {
    // 14 → 15 is 1/6 of the 6-day span: x=18.3, not the even 55.
    const days = ["2026-08-14", "2026-08-15", "2026-08-20"];
    expect(sparkSegments([10, 20, 30], days)).toEqual(["0,23 18.3,13", "110,3"]);
  });

  it("draws a flat series as the centre line", () => {
    const days = ["2026-08-14", "2026-08-15", "2026-08-16"];
    expect(sparkSegments([23, 23, 23], days)).toEqual(["0,13 55,13 110,13"]);
  });

  it("falls back to one sparkPoints segment on unusable days input", () => {
    // Length mismatch, garbage dates, non-increasing dates: never throw —
    // this renders on the public home.
    expect(sparkSegments([1, 2, 3], ["2026-08-14"])).toEqual([sparkPoints([1, 2, 3])]);
    expect(sparkSegments([1, 2], ["not-a-date", "2026-08-15"])).toEqual([
      sparkPoints([1, 2]),
    ]);
    expect(sparkSegments([1, 2], ["2026-08-15", "2026-08-14"])).toEqual([
      sparkPoints([1, 2]),
    ]);
  });

  it("handles empty and single-value series like sparkPoints", () => {
    expect(sparkSegments([], [])).toEqual([]);
    expect(sparkSegments([42], ["2026-08-15"])).toEqual(["0,13"]);
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
