import { expect, test } from "@playwright/test";

const MILK = "http://localhost:3000";

// Fixture pincodes (scripts/e2e-api.mjs seeds): 641001 covered (Coimbatore),
// 600001 TN-no-vendors (Chennai), 110001 out-of-area (non-TN).
test.describe("D28 pincode landing pages", () => {
  test("bare pincode 301s to /{city}/{pincode}", async ({ page }) => {
    await page.goto(`${MILK}/641001`);
    await expect(page).toHaveURL(`${MILK}/coimbatore/641001`);
    await expect(page.getByTestId("scope-covered")).toBeVisible();
  });

  test("covered landing is indexable with ItemList JSON-LD", async ({ page }) => {
    await page.goto(`${MILK}/coimbatore/641001`);
    await expect(page.locator('meta[name="robots"][content*="noindex"]')).toHaveCount(0);
    const jsonLd = page.locator('script[type="application/ld+json"]');
    await expect(jsonLd).toHaveCount(1);
    expect(await jsonLd.textContent()).toContain('"ItemList"');
    const canonical = page.locator('link[rel="canonical"]');
    await expect(canonical).toHaveAttribute("href", "https://milk.in/coimbatore/641001");
  });

  test("thin pincode self-noindexes", async ({ page }) => {
    await page.goto(`${MILK}/600001`); // redirects to /chennai/600001
    await expect(page).toHaveURL(`${MILK}/chennai/600001`);
    await expect(page.getByTestId("scope-tn-no-vendors")).toBeVisible();
    await expect(page.locator('meta[name="robots"][content*="noindex"]')).toHaveCount(1);
  });

  test("wrong city slug 301s to the canonical city", async ({ page }) => {
    await page.goto(`${MILK}/chennai/641001`);
    await expect(page).toHaveURL(`${MILK}/coimbatore/641001`);
  });

  test("out-of-area pincode renders in place (no city to redirect to)", async ({ page }) => {
    await page.goto(`${MILK}/110001`);
    await expect(page).toHaveURL(`${MILK}/110001`);
    await expect(page.getByTestId("scope-out-of-area")).toBeVisible();
    await expect(page.locator('meta[name="robots"][content*="noindex"]')).toHaveCount(1);
  });
});
