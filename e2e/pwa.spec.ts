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

  test("offline navigation falls back to the shell with helplines and last prices", async ({
    browser,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(`${MILK}/coimbatore/641001`); // registers SW + writes last-seen
    await page.waitForFunction(() => navigator.serviceWorker?.controller !== null, undefined, {
      timeout: 20_000,
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
