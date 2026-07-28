import { expect, test } from "@playwright/test";

import { MILK, fixtureSlug as seededSlug, waitForHeaderSettled } from "./helpers";

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
