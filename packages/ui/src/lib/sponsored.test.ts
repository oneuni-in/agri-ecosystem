import { describe, expect, it } from "vitest";

import { isSafeTargetUrl, parseServedAd } from "./sponsored";

const valid = {
  placement_id: "018f0000-0000-7000-8000-000000000001",
  creative_id: "018f0000-0000-7000-8000-000000000002",
  slot_key: "directory_browse",
  label: "sponsored",
  title: "Organic feed",
  body: "20% off",
  media_urls: ["https://media.example/x.jpg"],
  target_url: "https://example.com/offer",
};

describe("isSafeTargetUrl", () => {
  it("accepts absolute http(s)", () => {
    expect(isSafeTargetUrl("https://example.com/x")).toBe(true);
    expect(isSafeTargetUrl("http://example.com")).toBe(true);
  });
  it("rejects script/data/relative/other schemes", () => {
    expect(isSafeTargetUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeTargetUrl("data:text/html,x")).toBe(false);
    expect(isSafeTargetUrl("//example.com/x")).toBe(false);
    expect(isSafeTargetUrl("/relative")).toBe(false);
  });
});

describe("parseServedAd", () => {
  it("passes a valid payload through", () => {
    expect(parseServedAd(valid)).toEqual(valid);
  });
  it("rejects a missing or tampered label (unlabeled ads are forbidden)", () => {
    expect(parseServedAd({ ...valid, label: "organic" })).toBeNull();
    const { label: _label, ...rest } = valid;
    expect(parseServedAd(rest)).toBeNull();
  });
  it("rejects unsafe target urls", () => {
    expect(parseServedAd({ ...valid, target_url: "javascript:alert(1)" })).toBeNull();
  });
  it("rejects non-objects and null", () => {
    expect(parseServedAd(null)).toBeNull();
    expect(parseServedAd("x")).toBeNull();
  });
});
