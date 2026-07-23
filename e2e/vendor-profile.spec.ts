import { expect, type Page, test } from "@playwright/test";

const MILK = "http://localhost:3000";
const API = "http://localhost:8000";

/** Same convention as e2e/milk-home.spec.ts: wait out the silent-SSO bounce
 * before interacting. */
async function waitForHeaderSettled(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: /^login$/i })).toBeVisible({ timeout: 20_000 });
}

/** Resolve the seeded vendor's slug from the live API instead of hardcoding
 * it — survives seed renames. */
async function seededSlug(request: import("@playwright/test").APIRequestContext): Promise<string> {
  const res = await request.get(`${API}/catalog/milk/home/641001`);
  expect(res.ok()).toBeTruthy();
  const data = (await res.json()) as { vendors: { slug: string }[] };
  expect(data.vendors.length).toBeGreaterThan(0);
  return data.vendors[0].slug;
}

test.describe("D24 vendor profile", () => {
  test("renders with valid LocalBusiness JSON-LD (non-negotiable 2)", async ({
    page,
    request,
  }) => {
    const slug = await seededSlug(request);
    await page.goto(`${MILK}/directory/businesses/${slug}`);
    await waitForHeaderSettled(page);
    const raw = await page.locator('script[type="application/ld+json"]').first().textContent();
    expect(raw).toBeTruthy();
    const data = JSON.parse(raw as string) as Record<string, unknown>;
    expect(data["@context"]).toBe("https://schema.org");
    expect(data["@type"]).toBe("LocalBusiness");
    expect(data["name"]).toBeTruthy();
    expect(String(data["url"])).toContain(`/directory/businesses/${slug}`);
    const address = data["address"] as Record<string, unknown>;
    expect(address["@type"]).toBe("PostalAddress");
    expect(address["postalCode"]).toBe("641001");
  });

  test("guest sees login-gated contact, never a phone number", async ({ page, request }) => {
    const slug = await seededSlug(request);
    await page.goto(`${MILK}/directory/businesses/${slug}`);
    await waitForHeaderSettled(page);
    await expect(page.getByText(/login to view contact/i)).toBeVisible();
    // the seeded number must not be anywhere in the SSR payload
    const html = await page.content();
    expect(html).not.toContain("9876500023");
  });

  test("guest can send a contact lead via the form fallback", async ({ page, request }) => {
    const slug = await seededSlug(request);
    await page.goto(`${MILK}/directory/businesses/${slug}`);
    await waitForHeaderSettled(page);
    await page.getByLabel(/message/i).fill("Do you deliver on Sundays?");
    await page.getByRole("button", { name: /send enquiry/i }).click();
    await expect(page.getByText(/enquiry sent/i)).toBeVisible();
  });
});
