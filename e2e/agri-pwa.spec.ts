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
    // NOT the home (it streams a dozen Suspense boundaries, and hydration
    // finishing mid-evaluate destroys the execution context) and NOT
    // /offline either, which is the subtler trap: /offline is in PRECACHE,
    // so the worker's install FETCHES the very page the browser is sitting
    // on, `next dev` recompiles it underneath, and HMR reloads. Waiting for
    // networkidle narrows that race without closing it — it still failed
    // roughly one run in three. /categories is in neither PRECACHE nor
    // RUNTIME_CACHEABLE, so the worker never touches it. Registrations are
    // origin-scoped and this worker's scope is "/", so any same-origin page
    // answers the identical question.
    await page.goto(`${AGRI}/categories`);
    await page.waitForFunction(
      () => navigator.serviceWorker?.controller !== null,
      undefined,
      {
        timeout: 45_000,
      },
    );
    // Settle before evaluating, exactly as the API-cache test below does, and
    // for a reason specific to `next dev`: the worker's install FETCHES
    // /offline while the browser is sitting on /offline, so the dev server
    // recompiles the page underneath it and HMR reloads — destroying the
    // execution context mid-evaluate. Production has no HMR and never shows
    // this. Waiting for the network to go quiet lets that finish first.
    await page.waitForLoadState("networkidle");
    // Two workers on one scope fight over fetch handling and the loser's
    // cache goes quietly stale — A-U3 left room for ONE and this asserts we
    // took that room rather than adding a second.
    // Retried, because `next dev` can reload the page out from under an
    // evaluate: the worker's install fetches its precached routes, the dev
    // server compiles them on demand, and HMR reloads whatever is open —
    // "Execution context was destroyed". That navigation is benign and
    // cannot happen in production (no HMR, nothing compiled on demand), so
    // the right response is to ask again rather than widen a timeout or
    // weaken the claim. The assertion is unchanged: exactly one registration.
    await expect
      .poll(
        async () =>
          page
            .evaluate(
              async () =>
                (await navigator.serviceWorker.getRegistrations()).length,
            )
            .catch(() => null),
        { timeout: 45_000, intervals: [1_000] },
      )
      .toBe(1);
  });

  test("offline: helplines, last-known mandi prices and the shell all work", async ({
    browser,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();

    // Visit the routes first — /mandi and /account/saved are runtime-cached, not
    // precached, so a device only holds what its owner actually opened.
    await page.goto(`${AGRI}/helplines`);
    await page.waitForFunction(
      () => navigator.serviceWorker?.controller !== null,
      undefined,
      {
        timeout: 45_000,
      },
    );
    await page.goto(`${AGRI}/mandi`);
    await page.waitForLoadState("networkidle");

    await context.setOffline(true);

    // 1. A cached page comes back in full, not as the shell.
    await page.goto(`${AGRI}/helplines`).catch(() => undefined);
    // .first(): the number appears both in the header hotline chip and in
    // the band. Two hits is the page rendering fully, not a problem.
    await expect(
      page.getByRole("link", { name: /1800-180-1551/ }).first(),
    ).toBeVisible();

    // 2. Last-known mandi prices survive the network going away. The page
    //    carries its own as-of stamp, so a stale page still says how stale.
    await page.goto(`${AGRI}/mandi`).catch(() => undefined);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    // 3. Any OTHER navigation lands on the shell, which must be useful:
    //    it names what IS available offline rather than apologising.
    await page.goto(`${AGRI}/directory`).catch(() => undefined);
    await expect(
      page.getByRole("heading", { name: /offline/i }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /helpline/i }).first(),
    ).toBeVisible();

    await context.close();
  });

  test("API responses are never cached", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    // /categories rather than the home or /offline. The home streams a dozen
    // Suspense boundaries and hydration finishing mid-evaluate destroys the
    // execution context; /offline avoids that but is itself in PRECACHE, so
    // the worker's install refetches it and `next dev` recompiles the page
    // under the browser. /categories is cached by neither path. The Cache
    // Storage being inspected is origin-global, so this answers exactly the
    // same question without either race.
    await page.goto(`${AGRI}/categories`);
    await page.waitForFunction(
      () => navigator.serviceWorker?.controller !== null,
      undefined,
      {
        timeout: 45_000,
      },
    );
    await page.waitForLoadState("networkidle");
    // /account/saved is per-user, so an /api/* response in a shared cache would be a
    // PII leak. The worker returns early for that prefix; this proves it.
    // Retried for the same reason as the registration count above: a dev-only
    // HMR reload can destroy the execution context mid-evaluate. Returning
    // null on that (rather than []) matters — an errored probe must not be
    // mistaken for "no API entries cached", which is precisely what this test
    // exists to prove. Only a real, completed read can satisfy it.
    await expect
      .poll(
        async () =>
          page
            .evaluate(async () => {
              const names = await caches.keys();
              const found: string[] = [];
              for (const name of names) {
                const cache = await caches.open(name);
                for (const request of await cache.keys()) {
                  if (new URL(request.url).pathname.startsWith("/api/"))
                    found.push(request.url);
                }
              }
              return found;
            })
            .catch(() => null),
        { timeout: 45_000, intervals: [1_000] },
      )
      .toEqual([]);
    await context.close();
  });

  test("offline: /tools comes back as the real page, not the shell (AG-A12)", async ({
    browser,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();

    // Runtime-cached, so it is held only after a real visit — which is the
    // point: that visit is also what puts the page's JS in the HTTP cache.
    await page.goto(`${AGRI}/tools`);
    await page.waitForFunction(
      () => navigator.serviceWorker?.controller !== null,
      undefined,
      {
        timeout: 45_000,
      },
    );
    await page.waitForLoadState("networkidle");

    // A second visit, still online. The worker caches only what its own fetch
    // handler sees, and the first navigation of a session is served BEFORE
    // the worker controls the page — invisible to it, so it caches nothing.
    // Without this the offline hop below falls through to /offline, which is
    // the worker working correctly rather than a bug.
    await page.goto(`${AGRI}/tools`);
    await page.waitForLoadState("networkidle");

    await context.setOffline(true);
    await page.goto(`${AGRI}/tools`).catch(() => undefined);

    // The real page, not the /offline shell.
    await expect(page.getByLabel(/loan amount/i)).toBeVisible();
    await expect(page.getByTestId("emi-result")).toBeVisible();

    // WHY THIS STOPS SHORT OF COMPUTING, and where that proof lives instead.
    //
    // AG-A12 asks that the calculators WORK offline, and computing is the
    // part that matters. It cannot be proven here: this harness runs
    // `next dev`, which serves /_next/static/chunks/* with
    // `Cache-Control: no-store, must-revalidate`. no-store forbids the
    // browser from keeping them, so offline there is nothing to hydrate
    // from and every input sits at its default (650000/12.5%/84 -> the
    // ₹11,649 an earlier version of this test kept reading). That is the
    // dev server's instruction to the browser, not a flake and not
    // something a longer timeout or a better selector can reach.
    //
    // Production serves those chunks immutable, so a real visit leaves them
    // in the HTTP cache and hydration survives the network going away. That
    // is a different build, so it gets its own proof:
    // `node scripts/verify-offline-tools.mjs` (docs/qa/agri-offline-tools.md).
    await context.close();
  });
});
