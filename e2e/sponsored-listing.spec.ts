/**
 * M3.B sponsored listings, live stack. The e2e bootstrap seeds one GLOBAL
 * house sponsored-listing campaign (scripts/e2e-api.mjs passes
 * --with-sponsored-listing), so every covered landing page carries exactly
 * one sponsored card at position 1 of the primary ("Local vendors") grid.
 *
 * Locks the two page-level halves of the M3 non-negotiables:
 * - NN3: injection is render-layer only - every organic vendor the API
 *   returns still renders, and the JSON-LD ItemList never mentions the ad.
 * - NN4/labeling: the injected card carries "★ Sponsored".
 */
import { expect, test } from "@playwright/test";

import { API, MILK } from "./helpers";

test("sponsored listing injects at position 1, labeled, organic count unchanged", async ({
  page,
  request,
}) => {
  const home = await request.get(`${API}/catalog/milk/home/641001`);
  expect(home.ok()).toBeTruthy();
  const data = (await home.json()) as {
    vendors: { slug: string }[];
    brands: { slug: string }[];
  };
  expect(data.vendors.length).toBeGreaterThan(0);

  await page.goto(`${MILK}/coimbatore/641001`);

  const sponsoredCard = page.locator('[data-testid^="sponsored-listing-"]').first();
  await expect(sponsoredCard).toBeVisible();
  await expect(sponsoredCard).toContainText("★ Sponsored");

  // NN3 (page half): every organic card still renders - injection never
  // consumes an organic slot or touches the cursor stream. Scoped to the
  // results container: the Recommended rail above it re-renders VendorCards
  // (organic duplication by design) and must not skew this count.
  await expect(
    page.getByTestId("vendor-results").locator('[data-testid^="vendor-card-"]'),
  ).toHaveCount(data.vendors.length + data.brands.length);

  // Position 1: the sponsored card is the first cell of the primary grid.
  const primaryGrid = page
    .locator("section", { has: page.getByRole("heading", { name: "Local vendors" }) })
    .locator("div.grid")
    .first();
  await expect(primaryGrid.locator("> *").first()).toHaveAttribute(
    "data-testid",
    /^sponsored-listing-/,
  );
});

test("sponsored listings never enter the JSON-LD ItemList", async ({ page }) => {
  await page.goto(`${MILK}/coimbatore/641001`);
  const jsonLd = await page.locator('script[type="application/ld+json"]').first().textContent();
  expect(jsonLd).toBeTruthy();
  expect(jsonLd).toContain("ItemList");
  expect(jsonLd).not.toContain("Milk.in Partner Dairy"); // the house sponsored title
});
