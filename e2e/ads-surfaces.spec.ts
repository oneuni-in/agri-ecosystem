import { expect, test } from "@playwright/test";

import { MILK, VENDOR_PHONE, apiAs, fixtureSlug } from "./helpers";

/**
 * SPEC M2 non-negotiables on the live stack (house ads seeded + ads_enabled
 * flipped by scripts/e2e-api.mjs):
 * - DoD: house ads visible (global banner filled on home)
 * - NN2: impression beacon fires ONLY once the slot is scrolled into view;
 *   click beacon lands in D21 tracking
 * - NN3: CLS ~ 0 on home with the carousel live
 * (NN1 pending-never-serves is a backend test: test_ads_serve.py; partition
 * routing of beacon rows is test_ads_beacons.py/test_ads_migration.py.)
 */

test("global banner serves a labeled house ad on home", async ({ page }) => {
  await page.goto(`${MILK}/`);
  const banner = page.getByTestId("ad-carousel-milk_global_header");
  await expect(banner).toBeVisible();
  // A served house ad carries the wire label -> badge. If the engine were
  // dark we would see the unlabeled local fallback instead - fail loudly.
  await expect(banner.getByText("★ Sponsored").first()).toBeVisible({ timeout: 15_000 });
});

test("impression fires only when the slot becomes visible (NN2)", async ({ page }) => {
  // sendBeacon Blob bodies are not inspectable from Playwright (postData()
  // is null), so slots are distinguished by TIMING, not payload: settle the
  // above-the-fold beacons, snapshot the count, and require the off-screen
  // footer slot to add nothing until it is scrolled into view. Reduced
  // motion disables the banner autoplay so no new slide can beacon mid-test.
  let impressions = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/ads/impressions")) impressions += 1;
  });
  const ctx = await apiAs(VENDOR_PHONE);
  const slug = await fixtureSlug(ctx);
  await page.setViewportSize({ width: 390, height: 700 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`${MILK}/directory/businesses/${slug}`);
  const slot = page.getByTestId("ad-slot-milk_profile_footer");
  const unit = slot.getByTestId("ad-unit-milk_profile_footer");
  await expect(unit).toBeAttached({ timeout: 15_000 }); // serve resolved, ad rendered below fold
  await page.waitForTimeout(2000); // let above-the-fold impressions settle
  const before = impressions;
  await page.waitForTimeout(1000);
  expect(impressions).toBe(before); // still off-screen -> NO mount-fired beacon
  await unit.scrollIntoViewIfNeeded();
  await expect.poll(() => impressions, { timeout: 10_000 }).toBeGreaterThan(before);
});

test("click beacon lands in D21 tracking (NN2)", async ({ page }) => {
  const ctx = await apiAs(VENDOR_PHONE);
  const slug = await fixtureSlug(ctx);
  await page.goto(`${MILK}/directory/businesses/${slug}`);
  const slot = page.getByTestId("ad-slot-milk_profile_footer");
  await slot.scrollIntoViewIfNeeded();
  const unit = slot.getByTestId("ad-unit-milk_profile_footer");
  await expect(unit).toBeVisible({ timeout: 15_000 });
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/ads/clicks")),
    unit.click(),
  ]);
  // Body is not readable here: the same-origin house ad navigates the page
  // and Chromium discards the beacon response body. The 200 proves the click
  // reached the D21 tracking path; row-level partition assertions live in
  // backend test_ads_beacons.py / test_ads_migration.py.
  expect(response.status()).toBe(200);
});

test("home CLS stays ~0 with the carousel live (NN3)", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "layout-shift API is Chromium-only");
  // Collect via init script so the total survives an evaluate() race with
  // next-dev's HMR full reload (which destroys execution contexts); reading
  // is retried for the same reason - a reload re-runs the init script.
  await page.addInitScript(() => {
    interface ClsWindow {
      __cls?: number;
    }
    const w = window as ClsWindow;
    w.__cls = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as unknown as { value: number; hadRecentInput: boolean };
        if (!shift.hadRecentInput) w.__cls = (w.__cls ?? 0) + shift.value;
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
  await page.goto(`${MILK}/`);
  await page.waitForTimeout(3000); // let the carousel resolve + settle
  let cls = Number.NaN;
  for (let attempt = 0; attempt < 3 && Number.isNaN(cls); attempt++) {
    try {
      cls = await page.evaluate(() => (window as { __cls?: number }).__cls ?? 0);
    } catch {
      await page.waitForTimeout(1000); // context destroyed by a dev reload - retry
    }
  }
  expect(cls).toBeLessThan(0.02);
});
