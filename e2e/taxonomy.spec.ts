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

  /**
   * U4 A11 regression: the §5 pinned filters (Home delivery / Organic) must be
   * ABSENT from the DOM below 1024px, not merely `display:none` — U1's rule is
   * "filters leave the bar on mobile/tablet", and a hidden interactive element
   * is invisible to axe, which is exactly why the a11y gate never caught it.
   * Assert by COUNT, never by visibility.
   */
  test("§5 pinned filters are absent from the DOM below 1024 and pinned right above it", async ({
    page,
  }) => {
    const filters = page.getByTestId("category-bar-filters");
    await page.setViewportSize({ width: 360, height: 800 });
    await page.goto(`${MILK}/`);
    // Header settled = hydration done, so a zero count below is the island's
    // decision, not a page that has not hydrated yet (the SSR HTML does carry
    // the span — hidden — until React removes it).
    await waitForHeaderSettled(page);
    await expect(filters).toHaveCount(0);
    await page.setViewportSize({ width: 768, height: 900 });
    await expect(filters).toHaveCount(0);
    // Crossing the boundary re-mounts them live (matchMedia change event).
    await page.setViewportSize({ width: 1024, height: 900 });
    await expect(filters).toBeVisible();
    await expect(filters.locator("a")).toHaveCount(2);
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(filters).toBeVisible();
    // NN5 guard: with the filters pinned, the bar still never wraps — one row.
    const bar = await page.getByTestId("category-bar").boundingBox();
    expect(bar!.height).toBeLessThan(60);
  });

  test("the Tamil home renders Tamil category labels", async ({ page }) => {
    await page.goto(`${MILK}/ta`);
    await waitForHeaderSettled(page);
    await expect(categoryLink(page, "ghee")).toContainText("நெய்");
  });
});
