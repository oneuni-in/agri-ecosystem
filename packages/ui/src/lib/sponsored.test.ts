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

// --- M2 additions ---

import { isSafeMediaUrl, parseServeResponse, serveQuery } from "./sponsored";

const m2Ad = {
  ...valid,
  slot_key: "milk_global_header",
};

describe("isSafeMediaUrl", () => {
  it("mirrors the target_url gate", () => {
    expect(isSafeMediaUrl("https://media.example/a.jpg")).toBe(true);
    expect(isSafeMediaUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeMediaUrl("/relative.jpg")).toBe(false);
  });
});

describe("parseServeResponse", () => {
  it("reads the ads list", () => {
    expect(
      parseServeResponse({ ad: m2Ad, ads: [m2Ad, { ...m2Ad, placement_id: "p2" }] }),
    ).toHaveLength(2);
  });
  it("falls back to the legacy single ad", () => {
    expect(parseServeResponse({ ad: m2Ad })).toHaveLength(1);
  });
  it("NN1: drops entries without label sponsored", () => {
    expect(parseServeResponse({ ads: [{ ...m2Ad, label: "organic" }] })).toHaveLength(0);
  });
  it("strips unsafe media urls but keeps the ad", () => {
    const ads = parseServeResponse({ ads: [{ ...m2Ad, media_urls: ["javascript:alert(1)"] }] });
    expect(ads).toHaveLength(1);
    expect(ads[0]?.media_urls).toHaveLength(0);
  });
  it("returns [] on garbage", () => {
    expect(parseServeResponse(null)).toHaveLength(0);
    expect(parseServeResponse({ ad: null, ads: "x" })).toHaveLength(0);
    expect(parseServeResponse([m2Ad])).toHaveLength(0);
  });
});

describe("serveQuery", () => {
  it("builds slot + validated context", () => {
    const q = new URLSearchParams(
      serveQuery("milk_category_banner", {
        pincode: "641001",
        category: "ghee",
        count: 5,
        locale: "ta",
      }),
    );
    expect(q.get("slot")).toBe("milk_category_banner");
    expect(q.get("pincode")).toBe("641001");
    expect(q.get("category")).toBe("ghee");
    expect(q.get("count")).toBe("5");
    expect(q.get("locale")).toBe("ta");
  });
  it("omits malformed context instead of sending it", () => {
    const q = new URLSearchParams(
      serveQuery("s", { pincode: "abc", category: "Bad!", count: 1, locale: "xx" }),
    );
    expect(q.get("pincode")).toBeNull();
    expect(q.get("category")).toBeNull();
    expect(q.get("count")).toBeNull();
    expect(q.get("locale")).toBeNull();
  });
  it("caps count at 5", () => {
    expect(new URLSearchParams(serveQuery("s", { count: 99 })).get("count")).toBe("5");
  });
});
