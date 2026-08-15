import { describe, expect, it } from "vitest";

import {
  acresToHectares,
  emi,
  fertilizerPlan,
  seedRequirementKg,
  sprayMlPerTank,
  tanksPerAcre,
} from "./agri-calculators";

describe("emi", () => {
  it("computes the standard reducing-balance EMI (₹1L · 11% · 60m ≈ ₹2,174)", () => {
    expect(emi(100000, 11, 60)).toBe(2174);
  });

  it("handles r = 0 as straight division, not 0/0", () => {
    expect(emi(120000, 0, 12)).toBe(10000);
  });

  it("computes a typical tractor loan (₹6.5L · 12.5% · 84m)", () => {
    // cross-checked against a reducing-balance schedule
    expect(emi(650000, 12.5, 84)).toBe(11649);
  });

  it("returns 0 for degenerate inputs", () => {
    expect(emi(0, 11, 60)).toBe(0);
    expect(emi(100000, 11, 0)).toBe(0);
  });
});

describe("seedRequirementKg", () => {
  it("converts acres to hectares before applying the kg/ha rate", () => {
    // 30 kg/ha × 0.4047 ha = 12.141 → 12.1
    expect(seedRequirementKg("paddy-transplanted", 1)).toBe(12.1);
  });

  it("scales linearly with area", () => {
    // 75 × 2 × 0.4047 = 60.705 → 60.7
    expect(seedRequirementKg("paddy-direct", 2)).toBe(60.7);
  });

  it("returns 0 for non-positive area", () => {
    expect(seedRequirementKg("maize", 0)).toBe(0);
  });
});

describe("fertilizerPlan", () => {
  it("divides nutrient need by standard product fractions (1 ha ≈ 2.471 acres)", () => {
    const oneHaInAcres = 1 / acresToHectares(1); // exactly 1 ha
    const plan = fertilizerPlan({ n: 120, p: 40, k: 40 }, oneHaInAcres);
    expect(plan.urea).toBeCloseTo(120 / 0.46, 0); // ≈ 260.9
    expect(plan.dap).toBeCloseTo(40 / 0.46, 0); // ≈ 87.0
    expect(plan.mop).toBeCloseTo(40 / 0.6, 0); // ≈ 66.7
  });

  it("clamps negative doses (over-supplied soil) to zero product", () => {
    expect(fertilizerPlan({ n: -10, p: 0, k: 0 }, 1)).toEqual({ urea: 0, dap: 0, mop: 0 });
  });
});

describe("spray dilution", () => {
  it("ml per tank = label dose × tank litres", () => {
    expect(sprayMlPerTank(2, 16)).toBe(32);
    expect(sprayMlPerTank(2.5, 16)).toBe(40);
  });

  it("tanks per acre from the 200 L/acre knapsack planning volume", () => {
    expect(tanksPerAcre(16)).toBe(12.5);
    expect(tanksPerAcre(20)).toBe(10);
  });

  it("returns 0 for degenerate inputs", () => {
    expect(sprayMlPerTank(0, 16)).toBe(0);
    expect(tanksPerAcre(0)).toBe(0);
  });
});
