import { expect, test } from "@playwright/test";

import { MILK } from "./helpers";

/** Mirrors the lighthouserc.cjs 3G profile so the two gates agree on what
 * "slow" means. Those are kbps; CDP wants bytes/second. */
const THREE_G = {
  offline: false,
  latency: 150,
  downloadThroughput: (1638.4 * 1024) / 8,
  uploadThroughput: (675 * 1024) / 8,
};

/**
 * Measured, not guessed: four runs on mobile-chrome over the profile above
 * gave 18.6s / 19.5s / 21.1s / 21.5s. Budget = worst + ~60% headroom.
 *
 * This is a NEXT DEV server - JIT compilation, unbundled modules, no
 * production optimisation - so the absolute number says nothing about what a
 * real user experiences; `lighthouserc.cjs` audits the production build and
 * remains the actual performance gate. What this catches is a gross
 * regression, e.g. a change that doubles the work to first results.
 */
const BUDGET_MS = 35_000;

test.describe("D29 low-data / throttled 3G", { tag: "@matrix" }, () => {
  // CDP is Chromium-only - WebKit exposes no equivalent - so Safari's 3G
  // behaviour is an owner-run manual check, recorded in the matrix doc. This
  // is a capability exclusion, not a suppressed failure.
  test.skip(
    ({ browserName }) => browserName !== "chromium",
    "network throttling needs CDP, which only Chromium exposes",
  );

  test("the pincode page reaches usable results on 3G", async ({ page }) => {
    const client = await page.context().newCDPSession(page);
    await client.send("Network.enable");
    await client.send("Network.emulateNetworkConditions", THREE_G);

    const started = Date.now();
    await page.goto(`${MILK}/coimbatore/641001`);
    // "Usable" means the results are on screen, not merely that load fired.
    await expect(page.getByTestId("scope-covered")).toBeVisible({ timeout: 60_000 });
    const elapsed = Date.now() - started;

    console.log(`[d29] 3G time-to-results: ${elapsed}ms (budget ${BUDGET_MS}ms)`);
    expect(elapsed, `results took ${elapsed}ms on 3G`).toBeLessThan(BUDGET_MS);
  });

  test("low-data mode survives a reload and keeps the page usable on 3G", async ({ page }) => {
    const client = await page.context().newCDPSession(page);
    await client.send("Network.enable");
    await client.send("Network.emulateNetworkConditions", THREE_G);

    await page.goto(`${MILK}/coimbatore/641001`);
    await expect(page.getByTestId("scope-covered")).toBeVisible({ timeout: 60_000 });

    const toggle = page.getByTestId("low-data-toggle");
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    // Retry the click rather than assert once. LowDataToggle is a client
    // island, so a click landing before React attaches does nothing at all -
    // and on a phone profile over throttled 3G the bundle arrives late enough
    // that the default 5s assertion expires first (the one failure this spec
    // had on mobile-chrome in CI).
    await expect(async () => {
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-checked", "true", { timeout: 5_000 });
    }).toPass({ timeout: 60_000 });

    await page.reload();
    // Same hydration wait as pwa.spec.ts, and slower still: this page is under
    // 3G emulation, so the client bundle needed to correct the SSR "false"
    // arrives over a throttled link.
    await expect(page.getByTestId("low-data-toggle")).toHaveAttribute("aria-checked", "true", {
      timeout: 40_000,
    });
    // Degrading images must not cost the user the actual content.
    await expect(page.getByTestId("scope-covered")).toBeVisible({ timeout: 60_000 });
  });
});
