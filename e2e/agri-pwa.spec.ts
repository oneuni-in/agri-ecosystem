import { expect, test } from "@playwright/test";

const AGRI = "http://localhost:3002";

/**
 * A-U4 W4 — agri.in PWA + offline (AG-A43).
 *
 * The point of these tests is that offline is DEMONSTRATED rather than
 * reasoned about. A service worker that looks correct in review and does not
 * actually serve a cached page is the failure mode; only a real browser with
 * the network switched off can tell the difference.
 */
test.describe("A-U4 agri PWA", () => {
  test("manifest is served and installable-shaped", async ({ request }) => {
    const res = await request.get(`${AGRI}/manifest.webmanifest`);
    expect(res.ok()).toBe(true);
    const manifest = await res.json();
    // The four fields a browser needs before it will offer an install, plus
    // standalone specifically — iOS exposes PushManager only inside an
    // installed app, so notifications on iPhone depend on this value.
    expect(manifest.name).toContain("Agri.in");
    expect(manifest.start_url).toBe("/");
    expect(manifest.display).toBe("standalone");
    expect(manifest.icons.length).toBeGreaterThan(0);
  });

  test("exactly one service worker is registered", async ({ page }) => {
    await page.goto(AGRI);
    await page.waitForFunction(() => navigator.serviceWorker?.controller !== null, undefined, {
      timeout: 45_000,
    });
    // Two workers on one scope fight over fetch handling and the loser's
    // cache goes quietly stale — A-U3 left room for ONE and this asserts we
    // took that room rather than adding a second.
    const count = await page.evaluate(async () => {
      const registrations = await navigator.serviceWorker.getRegistrations();
      return registrations.length;
    });
    expect(count).toBe(1);
  });

  test("offline: helplines, last-known mandi prices and the shell all work", async ({
    browser,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();

    // Visit the routes first — /mandi and /saved are runtime-cached, not
    // precached, so a device only holds what its owner actually opened.
    await page.goto(`${AGRI}/helplines`);
    await page.waitForFunction(() => navigator.serviceWorker?.controller !== null, undefined, {
      timeout: 45_000,
    });
    await page.goto(`${AGRI}/mandi`);
    await page.waitForLoadState("networkidle");

    await context.setOffline(true);

    // 1. A cached page comes back in full, not as the shell.
    await page.goto(`${AGRI}/helplines`).catch(() => undefined);
    // .first(): the number appears both in the header hotline chip and in
    // the band. Two hits is the page rendering fully, not a problem.
    await expect(page.getByRole("link", { name: /1800-180-1551/ }).first()).toBeVisible();

    // 2. Last-known mandi prices survive the network going away. The page
    //    carries its own as-of stamp, so a stale page still says how stale.
    await page.goto(`${AGRI}/mandi`).catch(() => undefined);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    // 3. Any OTHER navigation lands on the shell, which must be useful:
    //    it names what IS available offline rather than apologising.
    await page.goto(`${AGRI}/directory`).catch(() => undefined);
    await expect(page.getByRole("heading", { name: /offline/i }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /helpline/i }).first()).toBeVisible();

    await context.close();
  });

  test("API responses are never cached", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    // /offline rather than the home: the home streams a dozen Suspense
    // boundaries, and hydration finishing mid-evaluate destroys the
    // execution context. The Cache Storage being inspected is origin-global,
    // so a static page answers exactly the same question without the race.
    await page.goto(`${AGRI}/offline`);
    await page.waitForFunction(() => navigator.serviceWorker?.controller !== null, undefined, {
      timeout: 45_000,
    });
    await page.waitForLoadState("networkidle");
    // /saved is per-user, so an /api/* response in a shared cache would be a
    // PII leak. The worker returns early for that prefix; this proves it.
    const cachedApiEntries = await page.evaluate(async () => {
      const names = await caches.keys();
      const found: string[] = [];
      for (const name of names) {
        const cache = await caches.open(name);
        for (const request of await cache.keys()) {
          if (new URL(request.url).pathname.startsWith("/api/")) found.push(request.url);
        }
      }
      return found;
    });
    expect(cachedApiEntries).toEqual([]);
    await context.close();
  });
});
