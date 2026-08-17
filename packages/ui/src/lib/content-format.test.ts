import { describe, expect, it } from "vitest";

import { extractFaq, formatDuration, helplineStamp } from "./content-format";

/**
 * A-U3 W2 — the three pure helpers on the content surfaces that could be
 * wrong quietly.
 *
 * extractFaq gets the most attention, and most of it is about what it
 * must REFUSE: FAQPage markup is a claim to a search engine that a page
 * answers questions, and making that claim falsely is penalised.
 */

describe("extractFaq", () => {
  it("finds pairs in a genuinely Q&A-shaped guide", () => {
    const body = [
      "When should I sow?",
      "After the first steady rain, once the soil holds a ball.",
      "How much seed per acre?",
      "Follow the TNAU rate for your variety.",
    ].join("\n");
    expect(extractFaq(body)).toEqual([
      {
        question: "When should I sow?",
        answer: "After the first steady rain, once the soil holds a ball.",
      },
      {
        question: "How much seed per acre?",
        answer: "Follow the TNAU rate for your variety.",
      },
    ]);
  });

  it("refuses a single pair — one Q&A is a sentence, not a FAQ", () => {
    expect(extractFaq("When should I sow?\nAfter the first rain.")).toEqual([]);
  });

  it("refuses prose that merely contains a rhetorical question", () => {
    const body = [
      "Milk yield falls before an animal looks unwell.",
      "So what actually helps?",
      "Shade, water and airflow, in that order.",
    ].join("\n");
    expect(extractFaq(body)).toEqual([]);
  });

  it("refuses questions with no answer after them", () => {
    expect(extractFaq("Is this a question?\nAnd another?")).toEqual([]);
  });

  it("gathers a multi-line answer up to the next question", () => {
    const body = ["Q one?", "line a", "line b", "Q two?", "line c"].join("\n");
    expect(extractFaq(body)).toEqual([
      { question: "Q one?", answer: "line a line b" },
      { question: "Q two?", answer: "line c" },
    ]);
  });

  it("works on Tamil bodies (all three locales use the ASCII ?)", () => {
    const body = [
      "எப்போது விதைக்க வேண்டும்?",
      "முதல் மழைக்குப் பிறகு.",
      "எவ்வளவு விதை தேவை?",
      "TNAU அளவைப் பின்பற்றுங்கள்.",
    ].join("\n");
    expect(extractFaq(body)).toHaveLength(2);
  });

  it("returns nothing for an empty body", () => {
    expect(extractFaq("")).toEqual([]);
  });
});

describe("formatDuration", () => {
  it("formats minutes and seconds", () => {
    expect(formatDuration(412)).toBe("6:52");
    expect(formatDuration(59)).toBe("0:59");
  });

  it("pads minutes once an hour is involved", () => {
    expect(formatDuration(3725)).toBe("1:02:05");
  });

  it("returns null when the duration is unknown", () => {
    expect(formatDuration(null)).toBeNull();
    expect(formatDuration(0)).toBeNull();
  });
});

describe("helplineStamp", () => {
  it("reports the OLDEST verification across the band", () => {
    expect(
      helplineStamp([
        { source: "agriwelfare.gov.in", verified_on: "2026-08-17" },
        { source: "dahd.gov.in", verified_on: "2026-08-14" },
      ]),
    ).toEqual({
      sources: "agriwelfare.gov.in · dahd.gov.in",
      date: "2026-08-14",
    });
  });

  it("de-duplicates sources", () => {
    expect(
      helplineStamp([
        { source: "x.gov.in", verified_on: "2026-08-14" },
        { source: "x.gov.in", verified_on: "2026-08-15" },
      ]).sources,
    ).toBe("x.gov.in");
  });

  it("is empty for an empty band", () => {
    expect(helplineStamp([])).toEqual({ sources: "", date: "" });
  });
});
