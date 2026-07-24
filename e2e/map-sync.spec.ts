import { expect, type Page, test } from "@playwright/test";

const MILK = "http://localhost:3000";

async function waitForHeaderSettled(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: /^login$/i })).toBeVisible({ timeout: 20_000 });
}

test.describe("D24 map ↔ list sync (non-negotiable 3)", () => {
  test("pin click highlights the card; card click highlights the pin", async ({ page }) => {
    await page.goto(`${MILK}/641001`);
    await waitForHeaderSettled(page);

    await page.getByTestId("map-toggle").click();
    await expect(page.getByTestId("vendor-map")).toBeVisible();

    // --- pin → card ---
    const pin = page.locator('[data-testid^="map-pin-"]').first();
    await expect(pin).toBeVisible({ timeout: 15_000 }); // marker mounts with the lazy chunk
    await pin.click();
    const selectedCard = page.locator('[data-testid^="vendor-card-"][data-selected="true"]');
    await expect(selectedCard).toBeVisible();

    // --- card → pin --- (click top-left corner: selection zone, no links there)
    const otherCard = page.locator('[data-testid^="vendor-card-"]').last();
    await otherCard.click({ position: { x: 8, y: 8 } });
    const otherId = await otherCard.getAttribute("data-card-id");
    const selectedPin = page.locator('[data-testid^="map-pin-"][data-selected="true"]');
    await expect(selectedPin).toBeVisible();
    await expect(selectedPin).toHaveAttribute("data-pin-id", otherId as string);
  });
});
