import { expect, type Page, test } from "@playwright/test";

// web-milk runs on :3000 but the Playwright baseURL is web-id (:3003),
// so every navigation here uses an absolute URL.
const MILK = "http://localhost:3000";

/**
 * Every page load races the header's `AuthCluster` silent-SSO probe (D10):
 * a fresh, cookie-less visitor bounces through `/api/auth/login?silent=1`
 * and back before settling (see e2e/sso.spec.ts, "fails gracefully for a
 * fresh visitor"). Interacting with the page before that round trip
 * resolves can hit a page that's mid-navigation and lose client state (e.g.
 * a form's in-progress submit) - so every test here waits for the header to
 * settle on its logged-out "Login" button first, same convention as sso.spec.ts.
 */
async function waitForHeaderSettled(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: /^login$/i })).toBeVisible({ timeout: 20_000 });
}

test.describe("D23 milk pincode home — three empty-state branches", () => {
  test("(a) covered TN pincode with a seeded vendor shows results", async ({ page }) => {
    await page.goto(`${MILK}/641001`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("scope-covered")).toBeVisible();
    await expect(page.getByTestId("type-filter-row")).toBeVisible();
    await expect(page.getByTestId("price-banner")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Local vendors/i })).toBeVisible();
  });

  test("(b) valid TN pincode with no vendors shows the warm district state + notify-me", async ({
    page,
  }) => {
    // 600001 (Chennai) is a real TN pincode in the geo fixture with no
    // business coverage — the seed only covers 641001 (Coimbatore).
    await page.goto(`${MILK}/600001`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("scope-tn-no-vendors")).toBeVisible();
    await expect(page.getByText(/No milk vendors in/i)).toBeVisible();
    await expect(page.getByTestId("notify-me")).toBeVisible();
  });

  test("(c) non-TN pincode shows the out-of-area state + notify-me", async ({ page }) => {
    // 110001 (Delhi) is not present in the geo fixture at all.
    await page.goto(`${MILK}/110001`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("scope-out-of-area")).toBeVisible();
    await expect(page.getByText(/live in Tamil Nadu/i)).toBeVisible();
    await expect(page.getByTestId("notify-me")).toBeVisible();
  });

  test("notify-me submits from the out-of-area state", async ({ page }) => {
    await page.goto(`${MILK}/110001`);
    await waitForHeaderSettled(page); // let the silent-SSO bounce finish before we click
    await page.getByRole("button", { name: /notify me/i }).click();
    await expect(page.getByTestId("notify-done")).toBeVisible();
  });
});
