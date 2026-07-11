import { describe, expect, it } from "vitest";

import { applyOtpInput } from "./otp";

describe("applyOtpInput", () => {
  it("types one digit and advances", () => {
    expect(applyOtpInput("", 0, "4", 6)).toEqual({ value: "4", focusIndex: 1 });
    expect(applyOtpInput("41", 2, "7", 6)).toEqual({ value: "417", focusIndex: 3 });
  });
  it("overwrites an existing digit", () => {
    expect(applyOtpInput("123456", 2, "9", 6)).toEqual({ value: "129456", focusIndex: 3 });
  });
  it("ignores non-digits", () => {
    expect(applyOtpInput("12", 2, "x", 6)).toEqual({ value: "12", focusIndex: 2 });
  });
  it("distributes a pasted code from any index", () => {
    expect(applyOtpInput("", 3, "123456", 6)).toEqual({ value: "123456", focusIndex: 5 });
    expect(applyOtpInput("99", 2, "1234", 6)).toEqual({ value: "991234", focusIndex: 5 });
  });
  it("strips separators from pasted text and clamps to length", () => {
    expect(applyOtpInput("", 0, "123-456-789", 6)).toEqual({ value: "123456", focusIndex: 5 });
  });
  it("stays on the last box when full", () => {
    expect(applyOtpInput("12345", 5, "6", 6)).toEqual({ value: "123456", focusIndex: 5 });
  });
});
