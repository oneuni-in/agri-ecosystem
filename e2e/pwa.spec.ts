import { expect, test } from "@playwright/test";

const MILK = "http://localhost:3000";

// The web-milk e2e server runs `next dev` with NEXT_PUBLIC_ENABLE_SW=1
// (playwright.config.ts) so the registration island is exercised for real.
test.describe("D28 PWA", () => {
  test("manifest is served and installable-shaped", async ({ request }) => {
    const res = await request.get(`${MILK}/manifest.webmanifest`);
    expect(res.ok()).toBe(true);
    const manifest = (await res.json()) as {
      display: string;
      start_url: string;
      theme_color: string;
      icons: { sizes: string; purpose?: string }[];
    };
    expect(manifest.display).toBe("standalone");
    expect(manifest.start_url).toBe("/");
    expect(manifest.icons.some((icon) => icon.sizes === "512x512")).toBe(true);
    expect(manifest.icons.some((icon) => icon.purpose === "maskable")).toBe(true);
  });

  test("layout links the manifest and theme color", async ({ page }) => {
    await page.goto(`${MILK}/`);
    await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
      "href",
      "/manifest.webmanifest",
    );
    await expect(page.locator('meta[name="theme-color"]').first()).toHaveAttribute(
      "content",
      /#[0-9A-Fa-f]{6}/,
    );
  });

  test("low-data toggle persists across reloads", async ({ page }) => {
    await page.goto(`${MILK}/`);
    const toggle = page.getByTestId("low-data-toggle");
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(await page.evaluate(() => document.cookie)).toContain("milk_lowdata=1");
    await page.reload();
    // 30s, not the 5s default: LowDataToggle is client-only
    // (useSyncExternalStore over document.cookie) and its SSR snapshot is
    // ALWAYS false by design, so ISR pages never vary on cookies. The server
    // therefore renders "false" after a reload and the client corrects it on
    // hydration - this assertion is really waiting for hydration, which on a
    // loaded CI runner takes longer than 5s (D29).
    await expect(page.getByTestId("low-data-toggle")).toHaveAttribute("aria-checked", "true", {
      timeout: 30_000,
    });
  });

  test("offline navigation falls back to the shell with helplines and last prices", async ({
    browser,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(`${MILK}/coimbatore/641001`); // registers SW + writes last-seen
    await page.waitForFunction(() => navigator.serviceWorker?.controller !== null, undefined, {
      // 45s: D29 roughly doubled this job's test count, so by the time the PWA
      // specs run the runner is busy and SW install+activate misses 20s.
      timeout: 45_000,
    });
    await context.setOffline(true);
    await page.goto(`${MILK}/my-needs`).catch(() => {
      /* navigation "fails" into the SW fallback — assert on the DOM below */
    });
    await expect(page.getByTestId("offline-shell")).toBeVisible();
    await expect(page.getByText("1962")).toBeVisible();
    await expect(page.getByText("1800-180-1551")).toBeVisible();
    await expect(page.getByTestId("offline-last-seen")).toContainText("641001");
    await context.close();
  });
});
