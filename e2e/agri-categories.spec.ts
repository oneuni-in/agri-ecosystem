/**
 * A-U1 CP3 — /categories, the /c/[slug] landings and /tools (build prompt
 * §4). Registry-driven means REGISTRY-driven: the tile count is asserted
 * against a live GET /catalog/verticals walk inside the test, never a
 * hardcoded list. No `waitUntil: "networkidle"` anywhere.
 */
import { expect, request, test } from "@playwright/test";

import { AGRI, API, waitForHeaderSettled } from "./helpers";

const GROUPS = new Set(["essentials", "inputs", "services", "community", "buy-sell"]);

interface VerticalWire {
  slug: string;
  nav_placement: { agri_home?: { group?: unknown } } | null;
}

/** The same bounded cursor walk lib/home.ts performs: every vertical with a
 * valid agri_home placement — the set the grid MUST equal (AG-A13). */
async function registrySlugs(): Promise<string[]> {
  const ctx = await request.newContext();
  const out: string[] = [];
  let cursor: string | null = null;
  for (let pageNo = 0; pageNo < 5; pageNo++) {
    const qs: string = cursor ? `?cursor=${encodeURIComponent(cursor)}&limit=50` : "?limit=50";
    const res = await ctx.get(`${API}/catalog/verticals${qs}`);
    expect(res.ok()).toBeTruthy();
    const body = (await res.json()) as { items: VerticalWire[]; next_cursor: string | null };
    for (const item of body.items) {
      const group = item.nav_placement?.agri_home?.group;
      if (typeof group === "string" && GROUPS.has(group)) out.push(item.slug);
    }
    if (!body.next_cursor) break;
    cursor = body.next_cursor;
  }
  await ctx.dispose();
  return out;
}

test.describe("A-U1 /categories — registry-driven grid", () => {
  test("tile count equals the registry count, tiles come from data", async ({
    page,
  }) => {
    const slugs = await registrySlugs();
    // Was `toBe(36)`. The count is not the property under test -- "the grid
    // comes from the registry rather than from hardcoded markup" is, and the
    // toHaveCount(slugs.length) below is what proves it. The literal only ever
    // proved that someone counted once, and it broke the moment a 37th
    // vertical arrived (agri-colleges, migration 0050). Moved, not weakened:
    // the floor still catches a registry that has collapsed or failed to load.
    expect(slugs.length).toBeGreaterThanOrEqual(36);

    await page.goto(`${AGRI}/categories`);
    await waitForHeaderSettled(page);
    // Every tile is a /c/{slug} link inside the filter island; nothing else
    // on this page links into /c/.
    await expect(page.locator('a[href^="/c/"]')).toHaveCount(slugs.length);
    // A slug the API returned appears as a tile — the grid renders the
    // registry, not a hardcoded list.
    const probe = slugs[0]!;
    await expect(page.locator(`a[href="/c/${probe}"]`)).toHaveCount(1);
    // The live/soon sub-line is data-derived; with 7 live in the registry
    // it must not claim anything else. Assert the counts line exists.
    await expect(page.getByText(/live now/).first()).toBeVisible();
  });

  test("?q= from the home search band pre-filters the grid", async ({ page }) => {
    const slugs = await registrySlugs();
    await page.goto(`${AGRI}/categories?q=seeds`);
    await waitForHeaderSettled(page);
    const filtered = page.locator('a[href^="/c/"]');
    await expect(page.locator('a[href="/c/seeds"]')).toHaveCount(1);
    expect(await filtered.count()).toBeLessThan(slugs.length);
  });
});

test.describe("A-U1 /c/[slug] — the shared vertical landing", () => {
  test("/c/seeds is noindexed and carries the notify-me form", async ({ page }) => {
    await page.goto(`${AGRI}/c/seeds`);
    await waitForHeaderSettled(page);
    await expect(page.locator('meta[name="robots"]').first()).toHaveAttribute(
      "content",
      /noindex/,
    );
    await expect(page.getByTestId("notify-me-form")).toHaveCount(1);
  });

  test("notify-me round-trip: 641001 lands a pincode-interest row via the real BFF", async ({
    page,
  }) => {
    await page.goto(`${AGRI}/c/seeds`);
    await waitForHeaderSettled(page); // let silent-SSO settle before submitting
    await page.getByLabel(/pincode/i).fill("641001");
    await page.getByRole("button", { name: /notify me/i }).click();
    await expect(page.getByTestId("notify-me-done")).toBeVisible();
  });

  test("/c/farm-tools (live) renders the door to /tools, no notify-me", async ({ page }) => {
    await page.goto(`${AGRI}/c/farm-tools`);
    await waitForHeaderSettled(page);
    await expect(page.locator('a[href="/tools"]')).toHaveCount(1);
    await expect(page.getByTestId("notify-me-form")).toHaveCount(0);
  });

  test("an unknown slug is a real 404, never a soft page", async ({ page }) => {
    const response = await page.goto(`${AGRI}/c/not-a-vertical`);
    expect(response?.status()).toBe(404);
  });
});

test.describe("A-U1 /tools — offline calculators", () => {
  test("EMI 100000 · 11% · 60m computes ₹2,174 with ZERO network requests", async ({ page }) => {
    await page.goto(`${AGRI}/tools`);
    await waitForHeaderSettled(page);
    // Count data requests made DURING the computation — the calculators are
    // client-pure (agri-calculators.ts) and must not fetch anything. Chunk
    // loads and HMR belong to the dev harness, so only fetch/xhr count.
    const computeRequests: string[] = [];
    page.on("request", (req) => {
      if (req.resourceType() === "fetch" || req.resourceType() === "xhr") {
        computeRequests.push(req.url());
      }
    });
    await page.getByLabel(/loan amount/i).fill("100000");
    await page.getByLabel(/interest rate/i).fill("11");
    await page.getByLabel(/tenure/i).fill("60");
    await expect(page.getByTestId("emi-result")).toHaveText("₹2,174");
    expect(computeRequests, "calculators must be offline-pure — no network during compute").toEqual(
      [],
    );
  });
});
