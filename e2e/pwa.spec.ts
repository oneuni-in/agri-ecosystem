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

  /**
   * U1 §10a — the price-alert opt-in card. Bound to the same D28 subscription
   * flow as the /notifications device toggle (lib/push.ts).
   *
   * What this suite can assert is the NEGATIVE half of "never nag": a browser
   * that has blocked notifications never sees the card, so the visitor is
   * never shown a button that could only fail.
   *
   * The positive half — card visible, naming the visitor's own pincode, and
   * dismissable — cannot run here at any permission setting: headless
   * Chromium reports `Notification.permission === "denied"` regardless of
   * Playwright's `grantPermissions`, because it has no notification backend to
   * grant. Verified instead in push-verification.spec.ts, which already runs
   * real Chrome for exactly this reason (`PUSH_VERIFY=1`).
   */
  test("§10a price-alert card stays hidden when notifications are blocked", async ({ page }) => {
    // The VAPID key IS provisioned in this config, so an absent card here
    // proves the permission gate rather than merely the feature-dark default.
    await page.goto(`${MILK}/en`);
    await expect(page.getByTestId("app-install-band")).toHaveCount(0); // not installable here either
    await page.waitForTimeout(2_000); // let the island's detect() settle before asserting absence
    await expect(page.getByTestId("price-alert-card")).toHaveCount(0);
  });

  /**
   * U1 §10b — the app/PWA install band. Chromium never fires
   * `beforeinstallprompt` under automation, so the Android path cannot be
   * asserted here; the iOS path can, and it is the one with a fallback worth
   * proving: Safari never fires the event at all, so the band must still
   * render with the Add-to-Home-Screen instruction and no dead Install button.
   */
  test("§10b install band falls back to the iOS hint with no install button", async ({
    browser,
  }) => {
    const context = await browser.newContext({
      userAgent:
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    });
    const page = await context.newPage();
    await page.goto(`${MILK}/en`);
    const band = page.getByTestId("app-install-band");
    await expect(band).toBeVisible({ timeout: 30_000 });
    await expect(band).toContainText(/add to home screen/i);
    await expect(band.getByRole("button", { name: /install/i })).toHaveCount(0);
    // "Dismissed stays dismissed": a 30-day cookie, shared with the fixed banner.
    await band.getByRole("button", { name: /dismiss/i }).click();
    await expect(band).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId("app-install-band")).toHaveCount(0);
    await context.close();
  });
});
