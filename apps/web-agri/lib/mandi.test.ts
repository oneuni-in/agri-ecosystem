import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { istHourLabel, nextPullDay } from "./mandi";

describe("istHourLabel (O1: the daily-cadence stamp's hour, from data)", () => {
  it.each([
    [0, "12 AM"],
    [8, "8 AM"],
    [11, "11 AM"],
    [12, "12 PM"],
    [19, "7 PM"], // settings.mandi_pull_hour_ist's current value
    [23, "11 PM"],
  ])("%i → %s", (hour, label) => {
    expect(istHourLabel(hour)).toBe(label);
  });
});

describe("nextPullDay (today/tomorrow by the IST clock)", () => {
  // 2026-08-20T00:00Z is 05:30 IST; 2026-08-20T14:00Z is 19:30 IST.
  it("before the pull hour → today", () => {
    expect(nextPullDay(19, new Date("2026-08-20T00:00:00Z"))).toBe("today");
  });
  it("after the pull hour → tomorrow", () => {
    expect(nextPullDay(19, new Date("2026-08-20T14:00:00Z"))).toBe("tomorrow");
  });
  it("IST midnight is hour 0, not 24 (h23 cycle)", () => {
    // 18:30Z = 00:00 IST — the next evening pull is still "today".
    expect(nextPullDay(19, new Date("2026-08-19T18:30:00Z"))).toBe("today");
  });
});

/**
 * AG-A68: the reference mockup's three "what farmers say" quotes
 * (agri_home_desktop_v1.html:1190-1192) are ILLUSTRATIVE design copy and
 * must never ship as app copy — the section renders approved D18 rows or
 * the empty-but-honest invitation, never invented testimonials. This
 * asserts the distinctive fragment of each quote appears nowhere in the
 * message catalogs or the section's source.
 */
describe("reference sample reviews never render (AG-A68)", () => {
  const SAMPLE_QUOTE_FRAGMENTS = [
    "sold at ₹4 more than the trader first offered",
    "தமிழில் கேட்டா தமிழில் பதில்",
    "Farmers from 3 nearby pincodes now call directly",
  ] as const;

  const sources = [
    resolve(process.cwd(), "app/home-sections.tsx"),
    resolve(process.cwd(), "../../packages/ui/src/i18n/messages/en.json"),
    resolve(process.cwd(), "../../packages/ui/src/i18n/messages/ta.json"),
    resolve(process.cwd(), "../../packages/ui/src/i18n/messages/hi.json"),
  ];

  it.each(sources)("%s contains none of the sample quotes", (file) => {
    const text = readFileSync(file, "utf8");
    for (const fragment of SAMPLE_QUOTE_FRAGMENTS) {
      expect(text).not.toContain(fragment);
    }
  });
});
