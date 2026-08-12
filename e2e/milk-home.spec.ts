import { expect, test } from "@playwright/test";

// web-milk runs on :3000 but the Playwright baseURL is web-id (:3003),
// so every navigation here uses an absolute URL.
import { MILK, waitForHeaderSettled } from "./helpers";

test.describe("D23 milk pincode home — three empty-state branches", () => {
  test("(a) covered TN pincode with a seeded vendor shows results", async ({ page }) => {
    await page.goto(`${MILK}/641001`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("scope-covered")).toBeVisible();
    await expect(page.getByTestId("type-filter-row")).toBeVisible();
    // U1b: the results page renders the §5b PriceTicker marquee (the same
    // catalog composite as the home) in place of the old dashed price box.
    await expect(page.getByTestId("price-ticker")).toBeVisible();
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
