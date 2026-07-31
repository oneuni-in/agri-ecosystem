import { describe, expect, it } from "vitest";

import { injectSponsored, isSafeTargetUrl, parseServedAd, type ServedAd } from "./sponsored";

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

describe("injectSponsored (M3 NN3)", () => {
  const ad = (id: string): ServedAd => ({
    ...valid,
    label: "sponsored",
    placement_id: id,
    slot_key: "milk_sponsored_listing",
  });
  const ads = [ad("a1"), ad("a2")];

  it("preserves organic order and identity exactly (sponsorship on)", () => {
    const organic = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }, { id: 5 }, { id: 6 }];
    const entries = injectSponsored(organic, ads);
    const organicOut = entries
      .filter((e) => e.kind === "organic")
      .map((e) => (e.kind === "organic" ? e.item : null));
    expect(organicOut).toEqual(organic);
    organicOut.forEach((item, i) => expect(item).toBe(organic[i]));
  });

  it("is the identity on the organic stream with sponsorship off", () => {
    const organic = [{ id: 1 }, { id: 2 }];
    const entries = injectSponsored(organic, []);
    expect(entries).toEqual(organic.map((item) => ({ kind: "organic", item })));
  });

  it("places sponsored entries at page positions 1 and 6", () => {
    const organic = Array.from({ length: 8 }, (_, i) => i);
    const entries = injectSponsored(organic, ads);
    expect(entries[0]?.kind).toBe("sponsored");
    expect(entries[5]?.kind).toBe("sponsored");
    expect(entries.filter((e) => e.kind === "sponsored")).toHaveLength(2);
    expect(entries).toHaveLength(10);
  });

  it("caps at 2 sponsored per page", () => {
    const five = [ad("1"), ad("2"), ad("3"), ad("4"), ad("5")];
    const entries = injectSponsored([1, 2, 3, 4, 5, 6, 7], five);
    expect(entries.filter((e) => e.kind === "sponsored")).toHaveLength(2);
  });

  it("appends past-the-end positions to short lists", () => {
    const entries = injectSponsored([1, 2, 3], ads);
    expect(entries[0]?.kind).toBe("sponsored");
    expect(entries[entries.length - 1]?.kind).toBe("sponsored");
    expect(entries.filter((e) => e.kind === "organic").map((e) => (e.kind === "organic" ? e.item : null))).toEqual([1, 2, 3]);
  });

  it("never injects into an empty organic list (no ad-only pages)", () => {
    expect(injectSponsored([], ads)).toEqual([]);
  });
});
