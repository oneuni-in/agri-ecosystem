import { expect, test } from "@playwright/test";

import { MILK, waitForHeaderSettled } from "./helpers";

/** A 1x1 transparent PNG — enough for MapLibre to consider a raster tile
 * loaded. */
const BLANK_TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

test.describe("D24 map ↔ list sync (non-negotiable 3)", () => {
  test("pin click highlights the card; card click highlights the pin", async ({ page }) => {
    // Serve OSM tiles locally. Two reasons, both load-bearing:
    //  - the suite otherwise reaches tile.openstreetmap.org from CI, an
    //    external network dependency in an e2e gate;
    //  - streaming real tiles keeps MapLibre repainting, and a marker whose
    //    transform is recomputed every frame never satisfies Playwright's
    //    stability check ("element is not stable"), so the click never lands.
    await page.route("https://tile.openstreetmap.org/**", (route) =>
      route.fulfill({ status: 200, contentType: "image/png", body: BLANK_TILE }),
    );

    await page.goto(`${MILK}/641001`);
    await waitForHeaderSettled(page);

    await page.getByTestId("map-toggle").click();
    await expect(page.getByTestId("vendor-map")).toBeVisible();

    // --- pin → card ---
    // Click the LAST pin, not `.first()`. Markers share one stacking context at
    // z-index auto, so the last one rendered paints on top and is the only one
    // guaranteed to receive the click. That matters because vendors sharing a
    // location genuinely overlap: the D27 demo import falls back to the pincode
    // centroid, stacking eight listings on one point locally, and
    // VendorMap.spread() separates duplicates by only ~1.3px at the zoom
    // fitBounds settles on. (See docs/qa/d29-device-matrix.md — that overlap is
    // a real D24 limitation, recorded rather than worked around here.) Pairing
    // via data-pin-id keeps this honest with 1 pin in CI or 50 locally.
    const pin = page.locator('[data-testid^="map-pin-"]').last();
    await expect(pin).toBeVisible({ timeout: 15_000 }); // marker mounts with the lazy chunk
    const pinId = await pin.getAttribute("data-pin-id");
    await pin.click();
    await expect(page.locator(`[data-card-id="${pinId}"]`)).toHaveAttribute(
      "data-selected",
      "true",
    );

    // --- card → pin --- (click top-left corner: selection zone, no links there)
    // Any card other than the one just selected; CI seeds a single vendor, so
    // fall back to it rather than skipping the direction entirely.
    const others = page.locator(`[data-testid^="vendor-card-"]:not([data-card-id="${pinId}"])`);
    const otherCard = (await others.count()) ? others.first() : page.locator(`[data-card-id="${pinId}"]`);
    await otherCard.click({ position: { x: 8, y: 8 } });
    const otherId = await otherCard.getAttribute("data-card-id");
    const selectedPin = page.locator('[data-testid^="map-pin-"][data-selected="true"]');
    await expect(selectedPin).toBeVisible();
    await expect(selectedPin).toHaveAttribute("data-pin-id", otherId as string);
  });
});
