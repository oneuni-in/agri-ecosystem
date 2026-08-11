import { expect, test, type Page } from "@playwright/test";

// web-milk runs on :3000 but the Playwright baseURL is web-id (:3003),
// so every navigation here uses an absolute URL.
import { MILK, waitForHeaderSettled } from "./helpers";

/**
 * U1 replaced the M1 category TILE ROW on the home with the reference's §5
 * category BAR (`HomeCategoryBar` → `CategoryBar`). The M1 requirement is
 * unchanged and still the point of these tests — the home's categories come
 * from the D17 schema, each links its `/p/{value}` page, and the labels
 * localise — so they now select the bar's links by href instead of the
 * removed `category-tile-*` test ids.
 */
const categoryLink = (page: Page, value: string) =>
  // Scoped to the bar: the §11 footer links the same three category pages, so
  // an unscoped href selector is a strict-mode violation, not a passing test.
  page.getByTestId("category-bar").locator(`a[href="/p/${value}"]`);

test.describe("M1 dairy taxonomy", () => {
  test("home renders the category bar from schema values", async ({ page }) => {
    await page.goto(`${MILK}/`);
    await waitForHeaderSettled(page);
    await expect(categoryLink(page, "milk")).toBeVisible();
    await expect(categoryLink(page, "ghee")).toBeVisible();
    // The value set is the schema's, not a hardcoded list: `khoa` is the value
    // U1's own binding-proof example adds, and it must be here with zero code.
    await expect(categoryLink(page, "khoa")).toBeVisible();
  });

  test("a category link navigates to its category page", async ({ page }) => {
    await page.goto(`${MILK}/`);
    await waitForHeaderSettled(page);
    await categoryLink(page, "ghee").click();
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
    // 30s: dev-JIT compiles the results route on first hit, and that cold
    // compile alone can outlast the 5s default (same class of trap as the
    // hydration race above — the click landed; the navigation is just slow).
    await expect(page).toHaveURL(/product_category=ghee/, { timeout: 30_000 });
  });

  test("the list-your-business CTA points at the console", async ({ page }) => {
    await page.goto(`${MILK}/`);
    await waitForHeaderSettled(page);
    // U1 §1: the CTA moved into the utility strip above the header.
    const cta = page.locator('a[href$="/business/listings"]').first();
    await expect(cta).toBeVisible();
    await expect(cta).toHaveAttribute("href", /\/business\/listings$/);
  });

  test("the Tamil home renders Tamil category labels", async ({ page }) => {
    await page.goto(`${MILK}/ta`);
    await waitForHeaderSettled(page);
    await expect(categoryLink(page, "ghee")).toContainText("நெய்");
  });
});
