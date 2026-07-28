import { expect, test, type Page } from "@playwright/test";

import { MILK, waitForHeaderSettled } from "./helpers";

/** 1x1 transparent PNG - enough for MapLibre to consider a tile loaded. */
const BLANK_TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

const MIN_TAP = 44; // design-system.md §1.5 - 44x44 CSS px

const ROUTES = ["/", "/coimbatore/641001", "/c/milk", "/search", "/post-need"];

/** Every visible, enabled control must be tappable with a thumb. Collects ALL
 * offenders in one pass - fixing them one failure per run wastes the point. */
async function tapTargetOffenders(page: Page, min: number) {
  return page.evaluate((limit) => {
    const out: { label: string; w: number; h: number; testid: string | null }[] = [];
    const nodes = document.querySelectorAll<HTMLElement>(
      "a[href], button, input, select, textarea, [role='button']",
    );
    for (const el of nodes) {
      if (el.hasAttribute("disabled") || el.getAttribute("aria-hidden") === "true") continue;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      // sr-only inputs are intentionally 1px; the visible <label> carries the
      // target (the `peer` pattern - see review-form.tsx).
      if (el.className.includes("sr-only")) continue;
      // `.tap-target` (packages/config/tailwind/preset.js) is the design
      // system's own answer to this rule: an ::after overlay sized
      // max(100%, 44px), which enlarges the HIT AREA without changing the
      // element's box. getBoundingClientRect cannot see it, so measuring the
      // box alone reports compliant controls - the 18px Data-saver switch
      // among them - as violations.
      if (el.classList.contains("tap-target")) continue;
      // Next.js dev-only affordances are not product UI.
      if (el.closest("[data-nextjs-toast], nextjs-portal")) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      if (r.width < limit || r.height < limit) {
        out.push({
          label: (el.getAttribute("aria-label") || el.textContent || el.tagName)
            .trim()
            .slice(0, 40),
          w: Math.round(r.width),
          h: Math.round(r.height),
          testid: el.getAttribute("data-testid"),
        });
      }
    }
    return out;
  }, min);
}

test.describe("D29 device matrix", { tag: "@matrix" }, () => {
  for (const route of ROUTES) {
    test(`tap targets on ${route}`, async ({ page }) => {
      await page.goto(`${MILK}${route}`);
      await page.waitForLoadState("networkidle");
      const offenders = await tapTargetOffenders(page, MIN_TAP);
      expect(
        offenders,
        `${route} has controls under ${MIN_TAP}px:\n${JSON.stringify(offenders, null, 2)}`,
      ).toEqual([]);
    });
  }

  test("the vendor map mounts and shows pins on a phone viewport", async ({ page }) => {
    // Serve tiles locally: keeps the suite off tile.openstreetmap.org and
    // stops MapLibre repainting, which otherwise leaves markers never
    // "stable" for a click (same reasoning as map-sync.spec.ts).
    await page.route("https://tile.openstreetmap.org/**", (route) =>
      route.fulfill({ status: 200, contentType: "image/png", body: BLANK_TILE }),
    );
    await page.goto(`${MILK}/coimbatore/641001`);
    // Header-settled, not networkidle: the silent-SSO bounce can still fire a
    // navigation after the network goes quiet, unmounting the map mid-click.
    await waitForHeaderSettled(page);
    await page.getByTestId("map-toggle").click();
    await expect(page.getByTestId("vendor-map")).toBeVisible();
    await expect(page.locator('[data-testid^="map-pin-"]').first()).toBeVisible({
      timeout: 20_000, // MapLibre ships as a lazy chunk
    });
  });
});
