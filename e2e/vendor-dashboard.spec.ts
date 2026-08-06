import { expect, test, type Page } from "@playwright/test";

import {
  API,
  VENDOR_PHONE,
  apiAs,
  fillOtp,
  peekOtp,
  randomPhone,
  resetOtpThrottle,
} from "./helpers";

// The vendor console (Task 11-15) lives ONLY in web-agri, whose dev server
// binds :3002 (D01-A port map) - not :3000 (that's web-milk). The task
// brief's skeleton had this wrong; playwright.config.ts was also missing a
// web-agri webServer entry (never added since D09/D10 wrote that file and
// neither of those specs touched web-agri) - fixed alongside this spec.
const AGRI = "http://localhost:3002";

/** Copied from e2e/post-need.spec.ts (D25) - not exported there. Resilient
 * to the dev-JIT hydration race (typed value can land before the island
 * hydrates, so Send OTP never enables) and walks the new-user handle-skip +
 * language steps before the pending /authorize resumes. */
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
  // step, pick a language - that finish()es into the authorize resume.
  await page.getByRole("button", { name: /skip for now/i }).click({ timeout: 20_000 });
  await page.getByRole("button", { name: /english/i }).click({ timeout: 20_000 });
}

test.describe("vendor dashboard (D26)", () => {
  test("console walk: listing -> coverage -> premium intent -> analytics -> inbox -> products", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    const phone = randomPhone();
    await resetOtpThrottle(phone);

    // Login: the protected /business/listings server-redirects to
    // /api/auth/login?next=... -> web-id /authorize -> /login (same BFF
    // dance D09/D10 use for milk/organic, just a different client_id/origin).
    await page.goto(`${AGRI}/business/listings`);
    await completeLoginResilient(page, phone);
    await page.waitForURL(new RegExp(`^${AGRI}/business/listings`), { timeout: 30_000 });

    // Listings: fresh vendor owns nothing yet -> the create-business form.
    await page.getByLabel("Business name").fill("E2E Dairy");
    await page.getByLabel("Primary pincode").fill("641001");
    await page.getByRole("button", { name: "Create listing" }).click();
    // dev-JIT first-POST compile can push this past 5s (D24/D25 trap); this
    // step chains create -> reload businesses -> per-selected detail fetch,
    // so give it more room than a single-request assertion. getByRole(combobox)
    // avoids getByLabel's ambiguity with the "Business console" nav landmark.
    await expect(page.getByRole("combobox", { name: "Business", exact: true })).toBeVisible({
      timeout: 25_000,
    });

    // Coverage: add + save.
    await page.getByLabel("Add pincode").fill("641001");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await page.getByRole("button", { name: "Save coverage" }).click();
    await expect(page.getByText("Coverage saved", { exact: false })).toBeVisible({
      timeout: 15_000,
    });

    // Premium: billing_enabled is ON globally for this whole e2e run (M5
    // Task 17's scripts/e2e-api.mjs flips it so advertiser-selfserve.spec.ts
    // can drive a real Razorpay-test-stub checkout) - so premium-client.tsx's
    // `billingLive` branch is always the live one here, not the pre-launch
    // "Choose premium" intent button (D20 dark-launch UI, now dead for this
    // suite). Assert the live branch instead: a fresh business with no
    // subscription shows "Manage subscription", which leads to the billing
    // page's "Free plan" state.
    await page.goto(`${AGRI}/business/premium`);
    await page.getByRole("link", { name: "Manage subscription" }).click();
    await expect(page.getByText("Free plan")).toBeVisible({ timeout: 15_000 });

    // Analytics: zero-state renders (no views/reveals/leads yet for this
    // brand-new business, but the stat tiles always render).
    await page.goto(`${AGRI}/business/analytics`);
    await expect(page.getByText("Profile views")).toBeVisible({ timeout: 15_000 });

    // Inbox: loads without error - empty for a business nobody has contacted.
    // ("Lead inbox" also appears in the nav link + h1, so match the precise
    // EmptyState title rather than a broad /lead/i that hits both of those.)
    await page.goto(`${AGRI}/business/inbox`);
    await expect(page.getByText("No leads yet.")).toBeVisible({ timeout: 15_000 });

    // Products: only exercised if the dev seed ships an active vertical
    // schema (migration 0018 seeds "milk", but don't hardcode that fact -
    // ask the live API, same as the task brief's DoD).
    const verticalsRes = await fetch(`${API}/catalog/verticals`);
    const verticals = verticalsRes.ok
      ? ((await verticalsRes.json()) as { items?: unknown[] }).items ?? []
      : [];
    if (verticals.length === 0) {
      console.log("SKIP: GET /catalog/verticals returned no items - products section skipped.");
    } else {
      await page.goto(`${AGRI}/business/products`);
      await expect(page.getByLabel(/milk type/i)).toBeVisible({ timeout: 15_000 });
      await page.getByLabel("Name", { exact: true }).fill("E2E Cow Milk 1L");
      // `category` is REQUIRED as of milk spec-schema v2 (M1, migration 0029)
      // and this form is schema-driven, so the field appeared here with no
      // console code change - which is the M1 integration surface working as
      // designed. Omitting it now 422s, so fill it like a real vendor would.
      await page.getByLabel(/^category/i).selectOption("milk");
      await page.getByLabel(/milk type/i).selectOption("cow");
      await page.getByRole("button", { name: "Add product" }).click();
      await expect(page.getByText("E2E Cow Milk 1L")).toBeVisible({ timeout: 15_000 });
    }
  });

  test("billing surface is live: M5 Task 17 flips billing_enabled globally for the e2e run", async () => {
    // ORIGINALLY this test proved the D20 dark-launch gate: billing_enabled
    // off -> 404, not 403 (modules/billing/router.py's _require_flag
    // documents "flag off -> this surface does not exist"), so an unlaunched
    // product stays invisible rather than merely refused. That flag-off
    // window no longer exists anywhere in this suite: M5 Task 17's
    // scripts/e2e-api.mjs now flips billing_enabled globally (via
    // seed_house_ads.py --enable-billing-flag) so
    // e2e/advertiser-selfserve.spec.ts can drive a real Razorpay-test-stub
    // ad-order checkout. The flag-OFF 404 behaviour itself is still covered
    // at the API level by modules/billing/router.py's own pytest suite
    // (test_billing_webhook.py et al., which enable/disable the flag
    // per-test) - this e2e test now asserts the flag-ON shape instead: the
    // routes exist, return 200, and a business with no subscription reads
    // back `subscription: null` plus the tier catalog, never a raw 404.
    // Asserted on the GETs, not POST /billing/subscriptions: FastAPI
    // validates a request body BEFORE the route body runs, so an empty POST
    // returns 422 without ever reaching _require_flag - which would prove
    // nothing about the gate. These carry no body and hit it directly.
    const vendor = await apiAs(VENDOR_PHONE);
    const subscription = await vendor.get("/billing/subscription");
    expect(subscription.status()).toBe(200);
    const subscriptionBody = await subscription.json();
    expect(subscriptionBody.subscription).toBeNull();
    expect(Array.isArray(subscriptionBody.tiers)).toBe(true);
    const invoices = await vendor.get("/billing/invoices");
    expect(invoices.status()).toBe(200);
    expect((await invoices.json()).items).toEqual([]);
    await vendor.dispose();
  });
});
