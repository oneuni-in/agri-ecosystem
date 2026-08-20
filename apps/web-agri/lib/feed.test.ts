import { describe, expect, it } from "vitest";

import { phraseFor, phrasesFor, type LiveFeedItem } from "./feed";

/** A wire row with every nullable field null; tests override what they need. */
function row(overrides: Partial<LiveFeedItem> & { kind: LiveFeedItem["kind"] }): LiveFeedItem {
  return {
    occurred_at: "2026-08-20T06:00:00Z",
    district: null,
    state: null,
    business_name: null,
    business_slug: null,
    rating: null,
    ...overrides,
  };
}

describe("phraseFor (O11: one localized phrase per kind, from payload fields only)", () => {
  it("need_posted with a district carries it", () => {
    expect(phraseFor(row({ kind: "need_posted", district: "Coimbatore" }))).toEqual({
      key: "needPosted",
      args: { hasDistrict: "yes", district: "Coimbatore" },
    });
  });

  it("need_posted without a district still renders (a complete sentence)", () => {
    expect(phraseFor(row({ kind: "need_posted" }))).toEqual({
      key: "needPosted",
      args: { hasDistrict: "no", district: "" },
    });
  });

  it("business_joined renders the public name", () => {
    expect(
      phraseFor(row({ kind: "business_joined", business_name: "Green Agro Traders" })),
    ).toEqual({ key: "businessJoined", args: { name: "Green Agro Traders" } });
  });

  it("business_joined without a name is SKIPPED — never an empty phrase", () => {
    expect(phraseFor(row({ kind: "business_joined" }))).toBeNull();
  });

  it("review_approved with name and rating carries both", () => {
    expect(
      phraseFor(row({ kind: "review_approved", business_name: "Sri Farm Supplies", rating: 5 })),
    ).toEqual({
      key: "reviewApproved",
      args: { hasName: "yes", name: "Sri Farm Supplies", hasRating: "yes", rating: 5 },
    });
  });

  it("review_approved with only a rating still renders", () => {
    expect(phraseFor(row({ kind: "review_approved", rating: 4 }))).toEqual({
      key: "reviewApproved",
      args: { hasName: "no", name: "", hasRating: "yes", rating: 4 },
    });
  });

  it("review_approved with only a name still renders", () => {
    expect(phraseFor(row({ kind: "review_approved", business_name: "AgroMart" }))).toEqual({
      key: "reviewApproved",
      args: { hasName: "yes", name: "AgroMart", hasRating: "no", rating: 0 },
    });
  });

  it("review_approved with neither name nor rating would render bare — SKIPPED", () => {
    expect(phraseFor(row({ kind: "review_approved" }))).toBeNull();
  });

  it("lead_sent renders the contacted business", () => {
    expect(phraseFor(row({ kind: "lead_sent", business_name: "Kisan Seeds Co" }))).toEqual({
      key: "leadSent",
      args: { name: "Kisan Seeds Co" },
    });
  });

  it("lead_sent without a name is SKIPPED", () => {
    expect(phraseFor(row({ kind: "lead_sent" }))).toBeNull();
  });

  it("an unknown future kind is skipped, not crashed on", () => {
    expect(phraseFor(row({ kind: "coin_minted" as LiveFeedItem["kind"] }))).toBeNull();
  });

  it("no phrase ever carries occurred_at — timestamps must not reach cached HTML", () => {
    const phrases = [
      phraseFor(row({ kind: "need_posted", district: "Erode" })),
      phraseFor(row({ kind: "business_joined", business_name: "X" })),
      phraseFor(row({ kind: "review_approved", business_name: "X", rating: 3 })),
      phraseFor(row({ kind: "lead_sent", business_name: "X" })),
    ];
    for (const phrase of phrases) {
      expect(Object.keys(phrase!.args)).not.toContain("occurred_at");
    }
  });
});

describe("phrasesFor (EMPTY MEANS ABSENT — the section-absence contract)", () => {
  it("null payload (flag off → 404, or engine down) → [] → section absent", () => {
    expect(phrasesFor(null)).toEqual([]);
  });

  it("empty items → [] → section absent, never recycled or padded", () => {
    expect(phrasesFor({ items: [] })).toEqual([]);
  });

  it("a feed whose every row is skipped → [] → section absent", () => {
    expect(
      phrasesFor({
        items: [row({ kind: "business_joined" }), row({ kind: "lead_sent" })],
      }),
    ).toEqual([]);
  });

  it("mixed feed keeps renderable rows in order and drops the rest", () => {
    const phrases = phrasesFor({
      items: [
        row({ kind: "need_posted", district: "Salem" }),
        row({ kind: "business_joined" }), // skipped: no name
        row({ kind: "lead_sent", business_name: "AgroMart" }),
      ],
    });
    expect(phrases.map((p) => p.key)).toEqual(["needPosted", "leadSent"]);
  });
});
