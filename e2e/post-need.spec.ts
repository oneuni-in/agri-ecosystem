import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import {
  API,
  MILK,
  VENDOR_PHONE,
  apiAs,
  fillOtp,
  peekOtp,
  randomPhone,
  resetOtpThrottle,
  waitForHeaderSettled,
} from "./helpers";

/** D25's vendor side is the D18 inbox API (the vendor console UI is D26). */
const vendorApi = (): Promise<APIRequestContext> => apiAs(VENDOR_PHONE);

/** Hydration-resilient variant of helpers.completeLoginUi: when this spec is
 * the first to touch /login, dev-JIT can hydrate the island AFTER the first
 * fill — the typed value then never reaches React state and Send OTP stays
 * SSR-disabled. Refill until the button reacts (proof hydration attached). */
async function completeLoginResilient(page: Page, phone: string): Promise<void> {
  const input = page.getByLabel(/mobile number/i);
  const send = page.getByRole("button", { name: /send otp/i });
  await input.waitFor({ timeout: 30_000 });
  await expect(async () => {
    await input.fill("");
    await input.fill(phone);
    await expect(send).toBeEnabled({ timeout: 2_000 });
  }).toPass({ timeout: 30_000 });
  await send.click();
  await expect(page.getByText(/6-digit code/i)).toBeVisible();
  await fillOtp(page, await peekOtp(`+91${phone}`));
  // fresh phones are always new users (progressive account): skip the handle
  // step, pick a language — that finish()es into the authorize resume.
  await page.getByRole("button", { name: /skip for now/i }).click({ timeout: 20_000 });
  await page.getByRole("button", { name: /english/i }).click({ timeout: 20_000 });
}

async function seededBusinessId(ctx: APIRequestContext): Promise<string> {
  const home = await ctx.get(`${API}/catalog/milk/home/641001`);
  expect(home.ok()).toBeTruthy();
  const data = (await home.json()) as { vendors: { slug: string }[] };
  expect(data.vendors.length).toBeGreaterThan(0);
  // Resolve the fixture BY SLUG, never by position. milk_home orders by
  // distance, so `vendors[0]` is whichever listing is nearest the pincode
  // centroid - a D27 seed vendor locally, the fixture only in CI. This context
  // is authenticated as the fixture's owner, so picking someone else's
  // business here fails the ownership check further down (D29).
  const fixture = data.vendors.find((v) => v.slug === "e2e-milk-vendor");
  expect(fixture, "seed fixture missing - run seed_e2e_milk.py").toBeTruthy();
  const biz = await ctx.get(`${API}/directory/businesses/${fixture!.slug}`);
  expect(biz.ok()).toBeTruthy();
  return ((await biz.json()) as { business: { id: string } }).business.id;
}

test.describe("D25 post my need", () => {
  test("post → routes to covering vendor → respond → user notified → fulfil", async ({
    page,
  }) => {
    const phone = randomPhone();
    await resetOtpThrottle(phone);

    // Snapshot the vendor's queue BEFORE posting. A local DB accumulates
    // "new" inquiries across runs (24 of them when this was written), so
    // matching merely on type+pincode picks up some earlier run's need,
    // belonging to a different random user - the response then lands on that
    // stale inquiry and THIS user's My-needs stays empty. CI never sees it
    // because its DB is fresh every run (D29).
    const vendor = await vendorApi();
    const businessId = await seededBusinessId(vendor);
    const before = await vendor.get(`/leads/inbox?business_id=${businessId}&status=new`);
    expect(before.ok()).toBeTruthy();
    const preexisting = new Set(
      ((await before.json()) as { items: { id: string }[] }).items.map((i) => i.id),
    );

    // 1. Guest fills the icon-first form at 641001, then goes through OTP —
    //    the draft survives the login round-trip (progressive account, D07/D11).
    await page.goto(`${MILK}/post-need`);
    await waitForHeaderSettled(page);
    await page.getByTestId("milk-type-cow").click();
    await page.getByTestId("schedule-daily").click();
    await page.getByTestId("time-morning").click();
    await page.getByTestId("need-pincode").fill("641001");
    await page.getByTestId("post-need-login").click(); // guest CTA → web-id OTP
    await completeLoginResilient(page, phone);
    await page.waitForURL(/post-need/, { timeout: 30_000 });
    await expect(page.getByTestId("need-pincode")).toHaveValue("641001"); // draft restored
    // dev-JIT can make the first authed submit slow (D24 lesson) — generous timeout
    await page.getByTestId("post-need-submit").click();
    const posted = page.getByTestId("need-posted");
    await expect(posted).toBeVisible({ timeout: 30_000 });
    await expect(posted).toContainText(/sent to [1-9]/i); // routed_count >= 1 (non-negotiable 1)

    // 2. Vendor sees it in the D18 inbox and responds via API.
    const inbox = await vendor.get(`/leads/inbox?business_id=${businessId}&status=new`);
    expect(inbox.ok()).toBeTruthy();
    const { items } = (await inbox.json()) as {
      items: { id: string; type: string; pincode: string }[];
    };
    const routed = items.find(
      (i) => !preexisting.has(i.id) && i.type === "milk_subscription" && i.pincode === "641001",
    );
    expect(routed, "no NEW inquiry reached the vendor for this run").toBeTruthy();
    const respond = await vendor.post(`/leads/inquiries/${routed!.id}/responses`, {
      data: { body: "We deliver daily at 6am. Fresh cow milk." },
    });
    expect(respond.status()).toBe(201);

    // 3. User sees the response + per-vendor status in My needs.
    await page.goto(`${MILK}/my-needs`);
    await expect(page.getByTestId("need-response").first()).toContainText(/6am/, {
      timeout: 20_000,
    });
    await expect(page.getByTestId("need-card").first()).toContainText(/responded/i);

    // 4. D12 notification landed (notify worker consumes lead.responded).
    await expect(async () => {
      await page.goto(`${MILK}/notifications`);
      await expect(page.getByText(/replied to your enquiry/i).first()).toBeVisible({
        timeout: 3_000,
      });
    }).toPass({ timeout: 30_000 }); // worker polls every ~2s

    // 5. Accept the vendor — both-side status closes out (non-negotiable 2).
    await page.goto(`${MILK}/my-needs`);
    await page.getByTestId("accept-vendor").first().click();
    await expect(page.getByTestId("need-status").first()).toContainText(/fulfilled/i, {
      timeout: 20_000,
    });

    await vendor.dispose();
  });

  test("no covering vendor → warm fallback, nothing routed", async ({ page }) => {
    const phone = randomPhone();
    await resetOtpThrottle(phone);
    await page.goto(`${MILK}/post-need`);
    await waitForHeaderSettled(page);
    await page.getByTestId("milk-type-cow").click();
    await page.getByTestId("need-pincode").fill("600001"); // TN + geocoded, zero coverage
    await page.getByTestId("post-need-login").click();
    await completeLoginResilient(page, phone);
    await page.waitForURL(/post-need/, { timeout: 30_000 });
    await expect(page.getByTestId("need-pincode")).toHaveValue("600001"); // draft restored
    await page.getByTestId("post-need-submit").click();
    await expect(page.getByTestId("need-no-coverage")).toBeVisible({ timeout: 30_000 });
  });
});
