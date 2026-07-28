import { expect, test } from "@playwright/test";

import {
  API,
  MILK,
  VENDOR_PHONE,
  WEBKIT_HTTP_COOKIE_SKIP,
  apiAs,
  completeLoginUi,
  completeNewUserSteps,
  fixtureSlug,
  randomPhone,
  waitForHeaderSettled,
} from "./helpers";

type InboxItem = { id: string; payload?: { source?: string } | null };

/** Reveal-attribution rows are inquiries carrying payload.source ==
 * 'contact_reveal' (modules/directory/analytics.py, leads_service.py:188). */
async function revealIds(
  ctx: import("@playwright/test").APIRequestContext,
  businessId: string,
): Promise<Set<string>> {
  const res = await ctx.get(`/leads/inbox?business_id=${businessId}&limit=100`);
  expect(res.ok()).toBeTruthy();
  const { items } = (await res.json()) as { items: InboxItem[] };
  return new Set(items.filter((i) => i.payload?.source === "contact_reveal").map((i) => i.id));
}

test.describe("D29 discover → call", { tag: "@matrix" }, () => {
  test.skip(({ browserName }) => browserName === "webkit", WEBKIT_HTTP_COOKIE_SKIP);

  test("guest discovers a vendor, logs in, reveals the number, and the reveal is tracked", async ({
    page,
    request,
  }) => {
    const vendor = await apiAs(VENDOR_PHONE);
    const slug = await fixtureSlug(request);
    const bizRes = await request.get(`${API}/directory/businesses/${slug}`);
    expect(bizRes.ok()).toBeTruthy();
    const businessId = ((await bizRes.json()) as { business: { id: string } }).business.id;

    // Snapshot first: a local DB accumulates reveals across runs, so only a
    // brand-new row proves THIS journey tracked (same lesson as post-need).
    const before = await revealIds(vendor, businessId);

    // --- discover: pincode home → tap Call on the vendor card ---
    // Canonical /{city}/{pincode} (D28), NOT the bare /641001, which 301s.
    await page.goto(`${MILK}/coimbatore/641001`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("scope-covered")).toBeVisible();
    // Let the page stop navigating before leaving it: a late client-side hop
    // back to /coimbatore/641001 otherwise interrupts the next navigation on
    // WebKit ("interrupted by another navigation").
    await page.waitForLoadState("networkidle");

    // Reach the profile the way a user does - the card's own Call CTA - rather
    // than a goto(). This is the "discover -> call" step the spec names.
    await page
      .getByTestId(`vendor-card-${slug}`)
      .getByRole("link", { name: /call/i })
      .click();
    await expect(page).toHaveURL(new RegExp(`/directory/businesses/${slug}`), { timeout: 30_000 });
    await waitForHeaderSettled(page);

    // --- guest is gated, and the number is not hiding in the SSR payload ---
    const gate = page.getByRole("link", { name: /login to view contact/i });
    await expect(gate).toBeVisible();
    expect(await page.content()).not.toContain("9876500023");

    // --- log in through the gate itself (BFF authorize dance, next= returns
    //     us to this business page) ---
    const phone = randomPhone();
    await gate.click();
    await completeLoginUi(page, phone);
    await completeNewUserSteps(page);
    await expect(page).toHaveURL(new RegExp(`/directory/businesses/${slug}`), { timeout: 30_000 });

    // --- reveal ---
    await page.getByRole("button", { name: /show phone number/i }).click();
    // CallButton renders <a href="tel:…>📞 Call</a> - assert the href, since
    // that is what actually places the call on a phone.
    await expect(page.locator('a[href^="tel:"]')).toBeVisible({ timeout: 15_000 });

    // --- tracked: exactly one NEW contact_reveal reached the vendor ---
    const after = await revealIds(vendor, businessId);
    const added = [...after].filter((id) => !before.has(id));
    expect(added, "the reveal did not produce a contact_reveal inquiry").toHaveLength(1);
    await vendor.dispose();
  });
});
