import { describe, expect, it } from "vitest";

import { deriveChecklist, isFirstRun } from "./account-roles";

/**
 * AG-U5 P6 — the first-run checklist.
 *
 * "Done-ness from real data, never clicks" is the rule this file defends. A
 * step is complete because the server holds the thing it asks for, so the
 * list survives a new device, a cleared cache and a different browser — and
 * cannot be ticked by visiting a page.
 */
const EMPTY = {
  pincode: null,
  interests: [] as string[],
  alerts: 0,
  threads: 0,
  saved: 0,
};

describe("deriveChecklist", () => {
  it("asks for four things, none of them done on a fresh account", () => {
    const steps = deriveChecklist(EMPTY);
    expect(steps).toHaveLength(4);
    expect(steps.every((step) => !step.done)).toBe(true);
  });

  it("ticks location off the stored pincode", () => {
    const steps = deriveChecklist({ ...EMPTY, pincode: "641001" });
    expect(steps.find((s) => s.id === "location")?.done).toBe(true);
    // and nothing else moved
    expect(steps.filter((s) => s.done)).toHaveLength(1);
  });

  it("ticks crops off the interests list", () => {
    const steps = deriveChecklist({ ...EMPTY, interests: ["tomato"] });
    expect(steps.find((s) => s.id === "crops")?.done).toBe(true);
  });

  it("ticks alerts off a real subscription", () => {
    expect(deriveChecklist({ ...EMPTY, alerts: 1 }).find((s) => s.id === "alerts")?.done).toBe(
      true,
    );
  });

  it("ticks asking off a real enquiry", () => {
    expect(deriveChecklist({ ...EMPTY, threads: 1 }).find((s) => s.id === "ask")?.done).toBe(true);
  });
});

describe("isFirstRun", () => {
  it("is true only while every step is still outstanding", () => {
    expect(isFirstRun(EMPTY)).toBe(true);
  });

  it("stops as soon as the person has done anything at all", () => {
    // One real action means they are not staring at an empty dashboard any
    // more, and the checklist should stop taking over the page.
    expect(isFirstRun({ ...EMPTY, pincode: "641001" })).toBe(false);
    expect(isFirstRun({ ...EMPTY, saved: 1 })).toBe(false);
  });

  it("counts a saved item even though no checklist step asks for one", () => {
    // Saving something is doing something. The checklist has four steps
    // because five is a wall, not because nothing else counts as a start.
    expect(isFirstRun({ ...EMPTY, saved: 2 })).toBe(false);
  });
});
