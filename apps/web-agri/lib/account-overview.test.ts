import { describe, expect, it } from "vitest";

import { countLabel, deriveCounts, quotesFor } from "./account-overview";

/**
 * AG-U5 P2 — the overview's stat row.
 *
 * The reference draws four exact numbers. None of the endpoints behind them
 * returns a total: they are cursor-paginated, so a "count" here is really
 * "how many we asked for and got". These tests pin the two things that makes
 * true — closed threads are not active, and a full page has to admit it may
 * not be the whole story.
 */
describe("deriveCounts", () => {
  const base = { inquiries: [], needs: [], alerts: [], saved: [], balance: 0 };

  it("counts an open enquiry and an open need together", () => {
    // The tile summarises the "My enquiries & needs" panel, so it counts what
    // that panel lists.
    const counts = deriveCounts({
      ...base,
      inquiries: [{ status: "new", responses: [] }],
      needs: [{ status: "open", routes: [] }],
    });
    expect(counts.activeThreads).toBe(2);
  });

  it("does not count closed threads as active", () => {
    const counts = deriveCounts({
      ...base,
      inquiries: [
        { status: "closed", responses: [] },
        { status: "responded", responses: [] },
      ],
      needs: [
        { status: "closed", routes: [] },
        { status: "fulfilled", routes: [] },
      ],
    });
    expect(counts.activeThreads).toBe(1);
  });

  it("counts how many businesses actually replied, not how many were asked", () => {
    const counts = deriveCounts({
      ...base,
      inquiries: [
        { status: "responded", responses: [{ id: "r1" }] },
        { status: "new", responses: [] },
      ],
      needs: [{ status: "open", routes: [{ responses: [{ id: "r2" }, { id: "r3" }] }] }],
    });
    expect(counts.replies).toBe(3);
  });

  it("carries the coin balance through untouched", () => {
    expect(deriveCounts({ ...base, balance: 1240 }).coins).toBe(1240);
    // null, not 0: an unreadable balance and a zero balance are different
    // claims, and only one of them is "you have no coins".
    expect(deriveCounts({ ...base, balance: null }).coins).toBe(null);
  });
});

describe("countLabel", () => {
  it("prints an exact count when the page was not full", () => {
    expect(countLabel(3, false)).toBe("3");
  });

  it("admits a full page might not be the whole story", () => {
    // Reading 20 of an unknown number and printing "20" states a total we
    // never asked for.
    expect(countLabel(20, true)).toBe("20+");
  });

  it("prints a plain zero, never '0+'", () => {
    expect(countLabel(0, false)).toBe("0");
    expect(countLabel(0, true)).toBe("0");
  });
});

describe("quotesFor", () => {
  it("totals the replies across a need's routed businesses", () => {
    const need = {
      status: "open",
      routes: [{ responses: [{ id: "a" }] }, { responses: [{ id: "b" }, { id: "c" }] }],
    };
    expect(quotesFor(need)).toBe(3);
  });

  it("is zero for a need nobody has answered", () => {
    expect(quotesFor({ status: "open", routes: [{ responses: [] }] })).toBe(0);
    expect(quotesFor({ status: "open", routes: [] })).toBe(0);
  });
});
