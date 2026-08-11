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

/**
 * The M2 DoD is "house ads visible on home", not "on slot milk_global_header".
 * U1 unmounted that slot from the milk layout (owner-approved: it is absent
 * from the approved reference and stacked a second ad unit directly above the
 * §3 hero) and the home's head banner is now the reference's own full-bleed
 * hero, `milk_home_hero_xl`. Same engine, same approved-only contract, same
 * always-on label — so the assertion moves with the surface. The slot key and
 * its house creatives still exist for the routes that have no hero.
 */
test("the home's head banner serves a labeled house ad", async ({ page }) => {
  await page.goto(`${MILK}/`);
  const banner = page.getByTestId("ad-carousel-milk_home_hero_xl");
  await expect(banner).toBeVisible();
  // A served house ad carries the wire label -> badge. If the engine were
  // dark we would see the unlabeled local fallback instead - fail loudly.
  await expect(banner.getByText("★ Sponsored").first()).toBeVisible({ timeout: 15_000 });
});

test("impression fires only when the slot becomes visible (NN2)", async ({ page }) => {
  // sendBeacon Blob bodies are not inspectable from Playwright (postData()
  // is null) - remove sendBeacon so the component's keepalive-fetch fallback
  // carries a readable JSON body, and assert per-slot on the payload.
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "sendBeacon", { value: undefined });
  });
  const footerBeacons: string[] = [];
  page.on("request", (request) => {
    if (!request.url().includes("/api/ads/impressions")) return;
    if ((request.postData() ?? "").includes("milk_profile_footer")) {
      footerBeacons.push(request.postData() ?? "");
    }
  });
  const ctx = await apiAs(VENDOR_PHONE);
  const slug = await fixtureSlug(ctx);
  await page.setViewportSize({ width: 390, height: 700 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`${MILK}/directory/businesses/${slug}`);
  const slot = page.getByTestId("ad-slot-milk_profile_footer");
  const unit = slot.getByTestId("ad-unit-milk_profile_footer");
  await expect(unit).toBeAttached({ timeout: 15_000 }); // serve resolved, ad rendered below fold
  await page.waitForTimeout(1500); // grace: a mount-fired beacon would land here
  expect(footerBeacons).toHaveLength(0); // still off-screen -> NO mount-fired beacon
  await unit.scrollIntoViewIfNeeded();
  await expect.poll(() => footerBeacons.length, { timeout: 10_000 }).toBeGreaterThan(0);
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
