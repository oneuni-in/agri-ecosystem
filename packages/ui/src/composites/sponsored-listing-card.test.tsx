// M3 NON-NEGOTIABLE 4: every paid unit carries the SponsoredBadge - locked
// by snapshot. Also locks: no "Recommended" label on any paid unit (M3.C)
// and the nofollow-sponsored rel contract.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ServedAd } from "../lib/sponsored";
import { SponsoredListingCard } from "./sponsored-listing-card";

const AD: ServedAd = {
  placement_id: "018f0000-0000-7000-8000-0000000000a1",
  creative_id: "018f0000-0000-7000-8000-0000000000c1",
  slot_key: "milk_sponsored_listing",
  label: "sponsored",
  title: "Kovai Fresh Dairy",
  body: "Farm milk in 641001",
  media_urls: [],
  target_url: "https://kovai.example.com/",
};

describe("SponsoredListingCard (M3 NN4)", () => {
  const html = renderToStaticMarkup(<SponsoredListingCard ad={AD} />);

  it("always carries the Sponsored badge", () => {
    expect(html).toContain("★ Sponsored");
  });

  it("never carries the organic Recommended label", () => {
    expect(html).not.toContain("Recommended");
  });

  it("is a nofollow-sponsored link to the ad target", () => {
    expect(html).toContain('rel="nofollow sponsored"');
    expect(html).toContain('href="https://kovai.example.com/"');
  });

  it("matches snapshot", () => {
    expect(html).toMatchSnapshot();
  });
});
