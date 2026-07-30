import { expect, test } from "@playwright/test";

// web-milk runs on :3000 but the Playwright baseURL is web-id (:3003),
// so every navigation here uses an absolute URL.
import { MILK, waitForHeaderSettled } from "./helpers";

test.describe("M1 dairy taxonomy", () => {
  test("home renders the category tile row from schema values", async ({ page }) => {
    await page.goto(`${MILK}/`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("category-tile-row")).toBeVisible();
    await expect(page.getByTestId("category-tile-milk")).toBeVisible();
    await expect(page.getByTestId("category-tile-ghee")).toBeVisible();
  });

  test("a tile navigates to its category page", async ({ page }) => {
    await page.goto(`${MILK}/`);
    await waitForHeaderSettled(page);
    await page.getByTestId("category-tile-ghee").click();
    await expect(page).toHaveURL(/\/p\/ghee$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/ghee/i);
  });

  test("the category page finder lands on a filtered pincode view", async ({ page }) => {
    await page.goto(`${MILK}/p/ghee`);
    await waitForHeaderSettled(page); // let the silent-SSO bounce finish before we type
    // `PincodeInput`'s Find button is disabled until 6 digits reach React
    // state, and dev-JIT can hydrate this island AFTER a first fill (same race
    // helpers.ts documents for /login). Refilling until the button enables is
    // the proof that hydration has attached.
    const input = page.getByRole("textbox", { name: /enter pincode/i });
    const find = page.getByRole("button", { name: /find milk/i });
    await expect(async () => {
      await input.fill("");
      await input.fill("641001");
      await expect(find).toBeEnabled({ timeout: 2_000 });
    }).toPass({ timeout: 30_000 });
    await find.click();
    // /{pincode} is the legacy shape and 301s to /{city}/{pincode} (D28)
    // carrying the query string, so assert on the filter, not the path.
    await expect(page).toHaveURL(/product_category=ghee/);
  });

  test("the list-your-business CTA points at the console", async ({ page }) => {
    await page.goto(`${MILK}/`);
    await waitForHeaderSettled(page);
    const cta = page.getByTestId("list-business-cta").first();
    await expect(cta).toBeVisible();
    await expect(cta).toHaveAttribute("href", /\/business\/listings$/);
  });

  test("the Tamil home renders Tamil category labels", async ({ page }) => {
    await page.goto(`${MILK}/ta`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("category-tile-ghee")).toContainText("நெய்");
  });
});
