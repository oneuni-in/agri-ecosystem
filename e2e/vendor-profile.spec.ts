import { expect, type Page, test } from "@playwright/test";

const MILK = "http://localhost:3000";
const API = "http://localhost:8000";

/** Same convention as e2e/milk-home.spec.ts: wait out the silent-SSO bounce
 * before interacting. */
async function waitForHeaderSettled(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: /^login$/i })).toBeVisible({ timeout: 20_000 });
}

/** Resolve the seeded vendor from the live API, BY SLUG rather than by
 * position: milk_home orders by distance from the pincode centroid, so
 * `vendors[0]` is a D27 seed listing locally and the fixture only in CI (D29).
 * Asserting against whichever vendor happens to be nearest makes the
 * phone-number and JSON-LD checks below meaningless. */
async function seededSlug(request: import("@playwright/test").APIRequestContext): Promise<string> {
  const res = await request.get(`${API}/catalog/milk/home/641001`);
  expect(res.ok()).toBeTruthy();
  const data = (await res.json()) as { vendors: { slug: string }[] };
  const fixture = data.vendors.find((v) => v.slug === "e2e-milk-vendor");
  expect(fixture, "seed fixture missing - run seed_e2e_milk.py").toBeTruthy();
  return fixture!.slug;
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
    // first POST after boot JIT-compiles the /api/leads route in dev — allow for it
    await expect(page.getByText(/enquiry sent/i)).toBeVisible({ timeout: 15_000 });
  });
});
