// e2e/advertiser-selfserve.spec.ts — M5 Task 17, the spec's headline
// non-negotiable NN1: a campaign created and paid in the wizard, approved in
// Ops, serves at the targeted pincode x category and NOT elsewhere.
//
// Runs against scripts/e2e-api.mjs's uvicorn (Task 17 additions): the
// Razorpay checkout is the `razorpay_test_stub` short-circuit
// (modules/billing/razorpay_client.py) - `create_payment_link`'s canned
// response is the callback_url itself, so "paying" just bounces the browser
// straight back to `/business/ads?paid={campaign_id}` with no real Razorpay
// account involved. The webhook is still the REAL signature-verified route
// (modules/billing/router.py razorpay_webhook) - this spec self-signs the
// `payment_link.paid` body with the e2e-api.mjs RAZORPAY_WEBHOOK_SECRET
// (`whsec_e2e`) exactly like modules/billing/ad_orders.py's applier expects,
// which is also how NN2 (forged/replayed webhook rejected) gets its own
// in-e2e coverage alongside NN1.
//
// billing_enabled is flipped ON globally for the whole e2e run by
// scripts/e2e-api.mjs (seed_house_ads.py --enable-billing-flag) - see
// e2e/vendor-dashboard.spec.ts for the console-regression fallout of that
// (its former billing-dark 404 assertions became billing-live 200 ones).
import crypto from "node:crypto";

import { expect, test, type Locator } from "@playwright/test";

import {
  AGRI,
  API,
  WEBKIT_HTTP_COOKIE_SKIP,
  apiAs,
  completeLoginUi,
  completeNewUserSteps,
  randomPhone,
  resetOtpThrottle,
  staffApi,
} from "./helpers";

const SECRET = "whsec_e2e"; // scripts/e2e-api.mjs RAZORPAY_WEBHOOK_SECRET
const PINCODE = "641001"; // Coimbatore centroid - the D23 fixture pincode, already geo-loaded
const OFF_PINCODE = "600001"; // Chennai - same state (Tamil Nadu), different pincode/district
const OFFER_URL = "https://example.com/offer";

// A real, decodable 1x1 transparent PNG (shared/media.py's reencode_image
// opens it with Pillow - junk bytes 422 as `unsupported_type`, so this must
// be a genuine image, not arbitrary bytes with a .png name).
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

function signed(body: object): { raw: string; headers: Record<string, string> } {
  const raw = JSON.stringify(body);
  const signature = crypto.createHmac("sha256", SECRET).update(raw).digest("hex");
  return {
    raw,
    headers: {
      "x-razorpay-signature": signature,
      "x-razorpay-event-id": `evt_e2e_${Date.now()}_${Math.random().toString(36).slice(2)}`,
      "content-type": "application/json",
    },
  };
}

function paidWebhookBody(args: {
  plinkId: string;
  orderId: string;
  paymentId: string;
  amountPaise: number;
}): object {
  // Shape modules/billing/ad_orders.py's apply_payment_link_paid reads via
  // _nested_entity(payload, "payload", "payment_link"|"payment", "entity") -
  // pinned by backend/core/tests/test_billing_ad_webhook.py's own `_paid_body`.
  return {
    event: "payment_link.paid",
    payload: {
      payment_link: { entity: { id: args.plinkId, reference_id: args.orderId } },
      payment: { entity: { id: args.paymentId, amount: args.amountPaise } },
    },
  };
}

/** Direct-to-API serve probe (no proxy, no location cookie ambiguity - the
 * web-agri /api/ads/serve proxy derives pincode from the agri_loc cookie,
 * never a query param, per apps/web-agri/app/api/ads/[...path]/route.ts).
 * House ads may serve alongside ours (M5 decisions), so callers must assert
 * on OUR creative's presence/absence via target_url, never `ad === null`.
 * count=5 (service.MAX_SERVE_COUNT) so a matching campaign is deterministically
 * included when eligible - the pool of matching placements per slot is tiny
 * (2 house + at most 1 of ours), so a high count drains the whole pool
 * instead of leaving OUR placement to weighted-random luck on count=1. */
async function servesOurOffer(params: Record<string, string>): Promise<boolean> {
  const url = new URL(`${API}/ads/serve`);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  url.searchParams.set("count", "5");
  const res = await fetch(url.toString());
  expect(res.ok, `GET ${url} -> ${res.status}`).toBeTruthy();
  const body = (await res.json()) as { ads: { target_url: string }[] };
  return body.ads.some((ad) => ad.target_url.includes("example.com/offer"));
}

test.describe("M5 advertiser self-serve (Task 17, NN1/NN2)", () => {
  test("create -> pay(test) -> approve -> serves targeted-only, rejects forged/replayed webhooks", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const phone = randomPhone();

    // --- 1. New phone -> login on /business/ads (BFF authorize dance, same
    // as vendor-dashboard.spec.ts's completeLoginResilient) -----------------
    await resetOtpThrottle(phone);
    await page.goto(`${AGRI}/business/ads`);
    await completeLoginUi(page, phone);
    await completeNewUserSteps(page); // fresh phone = progressive account (skip handle, pick language)
    await page.waitForURL(new RegExp(`^${AGRI}/business/ads`), { timeout: 30_000 });

    // --- create a business at 641001 (listings-page helper, vendor-dashboard
    // .spec.ts precedent) - /business/ads shows "Create a listing first"
    // until one exists. -----------------------------------------------------
    await page.goto(`${AGRI}/business/listings`);
    await page.getByLabel("Business name").fill("E2E Ad Advertiser Co");
    await page.getByLabel("Primary pincode").fill(PINCODE);
    await page.getByRole("button", { name: "Create listing" }).click();
    // 45s, not vendor-dashboard.spec.ts's 25s: that spec LOGS IN on
    // /business/listings, so the route is already compiled by the time it
    // clicks. This one logs in on /business/ads and only then navigates
    // here, so the click chains a cold `next dev` compile of BOTH
    // /business/listings and the POST /api/businesses proxy route before
    // the create -> reload -> per-business detail fetch even starts.
    await expect(page.getByRole("combobox", { name: "Business", exact: true })).toBeVisible({
      timeout: 45_000,
    });

    // --- 2. The wizard -------------------------------------------------
    await page.goto(`${AGRI}/business/ads`);
    await page.getByRole("button", { name: "New campaign" }).click();

    // Step 1: Goal - banner ads, home hero slot (milk_home_hero).
    await page.getByLabel("Campaign name").fill("E2E ghee push");
    await page.getByRole("radio", { name: /banner ads/i }).click();
    await page.getByRole("checkbox", { name: /home page hero/i }).check();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    // Step 2: Categories - ghee only (uncheck "All categories" first).
    await page.getByRole("checkbox", { name: /all categories/i }).uncheck();
    const gheeCheckbox = page.getByRole("checkbox", { name: /^ghee$/i });
    await expect(gheeCheckbox).toBeVisible({ timeout: 15_000 }); // /catalog/verticals/milk/schema fetch
    await gheeCheckbox.check();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    // Step 3: Areas - specific pincode 641001.
    await page.getByRole("radio", { name: /specific pincodes/i }).click();
    await page.getByPlaceholder("6-digit pincode").fill(PINCODE);
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByText(PINCODE)).toBeVisible();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    // Step 4: Schedule & budget - today..+14, 10k views. "Save & continue"
    // persists the draft server-side (POST /api/ads/my/campaigns) - capture
    // that response directly for the campaign id + server-priced total,
    // rather than re-deriving either client-side.
    const today = new Date();
    const flightStart = today.toISOString().slice(0, 10);
    const flightEndDate = new Date(today);
    flightEndDate.setUTCDate(flightEndDate.getUTCDate() + 14);
    const flightEnd = flightEndDate.toISOString().slice(0, 10);
    await page.getByLabel("Start date").fill(flightStart);
    await page.getByLabel("End date").fill(flightEnd);
    await page.getByRole("button", { name: "10k" }).click();

    const [createResponse] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().endsWith("/api/ads/my/campaigns") && r.request().method() === "POST",
      ),
      page.getByRole("button", { name: "Save & continue" }).click(),
    ]);
    expect(createResponse.ok()).toBeTruthy();
    const createdCampaign = (await createResponse.json()) as { id: string; price_paise: number };
    const campaignId = createdCampaign.id;
    // Server-side non-zero total, proven at the source (pricing.py's
    // ghee multiplier x tier CPM x 10,000 views is always > the rate
    // card's min_total_paise floor) - never derived client-side.
    expect(createdCampaign.price_paise).toBeGreaterThan(0);

    // Step 5: Creatives - tiny PNG + English copy + an https target.
    await expect(page.getByText(/Add up to \d+ creatives/i)).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Add a creative" }).click();
    await page
      .getByLabel("Image (optional)")
      .setInputFiles({ name: "pixel.png", mimeType: "image/png", buffer: TINY_PNG });
    await page.getByLabel("Title (English)").fill("Fresh ghee, delivered");
    await page.getByLabel("Body (English)").fill("Farm-fresh ghee at your door.");
    await page.getByLabel("Target URL").fill(OFFER_URL);

    const [creativeResponse] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().endsWith(`/api/ads/my/campaigns/${campaignId}/creatives`) &&
          r.request().method() === "POST",
      ),
      page.getByRole("button", { name: "Add creative", exact: true }).click(),
    ]);
    expect(creativeResponse.ok()).toBeTruthy();
    const createdCreative = (await creativeResponse.json()) as { id: string; target_url: string };
    const creativeId = createdCreative.id;
    expect(createdCreative.target_url).toBe(OFFER_URL);

    await page.getByRole("button", { name: "Next", exact: true }).click();

    // Step 6: Review & pay - server-truth quote shows a non-zero ₹ total,
    // then Pay bounces (via the test stub) back to /business/ads?paid=...
    const payButton = page.getByRole("button", { name: /securely with razorpay/i });
    await expect(payButton).toBeEnabled({ timeout: 15_000 });
    // The total carries paise whenever GST lands on a fractional rupee, and the
    // tier behind the price differs between a tier-loaded dev DB and CI's
    // (geo-only) e2e seed - so accept an optional decimal part.
    const payButtonText = (await payButton.textContent()) ?? "";
    expect(payButtonText).toMatch(/Pay ₹[\d,]+(\.\d{1,2})? securely with Razorpay/);
    expect(payButtonText).not.toMatch(/Pay ₹0(\.0+)? securely/);

    await Promise.all([
      page.waitForURL(new RegExp(`^${AGRI}/business/ads\\?paid=`), { timeout: 45_000 }),
      payButton.click(),
    ]);
    const paidUrl = new URL(page.url());
    expect(paidUrl.searchParams.get("paid")).toBe(campaignId);

    // --- 3. Read the order, self-sign + POST the payment_link.paid webhook -
    const advertiser = await apiAs(phone);
    const ordersRes = await advertiser.get(`/billing/ad-orders?campaign_id=${campaignId}`);
    expect(ordersRes.ok()).toBeTruthy();
    const ordersBody = (await ordersRes.json()) as {
      items: { id: string; total_paise: number; status: string }[];
    };
    expect(ordersBody.items.length).toBeGreaterThan(0);
    const order = ordersBody.items[0];
    expect(order.status).toBe("created");
    const totalPaise = order.total_paise;
    expect(totalPaise).toBeGreaterThan(0);
    // razorpay_client.py's stub derives the plink id deterministically from
    // the order id (`reference_id`) at create_payment_link time -
    // `f"plink_test_{reference_id.replace('-', '')[:14]}"` - AdOrderOut
    // deliberately never exposes razorpay_plink_id on the wire (money-path
    // review), so this mirrors that exact formula rather than adding a field.
    const plinkId = `plink_test_${order.id.replace(/-/g, "").slice(0, 14)}`;

    const paidBody = paidWebhookBody({
      plinkId,
      orderId: order.id,
      paymentId: "pay_e2e_1",
      amountPaise: totalPaise,
    });
    const { raw: paidRaw, headers: paidHeaders } = signed(paidBody);
    const webhookRes = await fetch(`${API}/billing/webhook/razorpay`, {
      method: "POST",
      body: paidRaw,
      headers: paidHeaders,
    });
    expect(webhookRes.status).toBe(200);
    expect((await webhookRes.json()).status).toBe("ok");

    // --- 4. UI reflects payment; staff approves the creative ---------------
    await expect(page.getByText("Payment received — your ads are in review.")).toBeVisible({
      timeout: 30_000,
    });

    const staff = await staffApi();
    const queueRes = await staff.get("/admin/moderation/queue?type=creative&limit=100");
    expect(queueRes.ok()).toBeTruthy();
    const queueBody = (await queueRes.json()) as { items: { id: string }[] };
    expect(
      queueBody.items.some((item) => item.id === creativeId),
      "our pending creative was not found in the moderation queue",
    ).toBeTruthy();

    const approveRes = await staff.post(`/admin/moderation/creative/${creativeId}/approve`, {
      data: {},
    });
    expect(approveRes.ok()).toBeTruthy();
    await staff.dispose();

    const campaignAfterApproval = await advertiser.get(`/ads/my/campaigns/${campaignId}`);
    expect(campaignAfterApproval.ok()).toBeTruthy();
    expect((await campaignAfterApproval.json()).status).toBe("active");

    // --- 5. Serve assertions: the heart of NN1 ------------------------------
    expect(
      await servesOurOffer({ slot: "milk_home_hero", pincode: PINCODE, category: "ghee" }),
      "creative must serve at its targeted pincode x category",
    ).toBe(true);
    expect(
      await servesOurOffer({ slot: "milk_home_hero", pincode: OFF_PINCODE, category: "ghee" }),
      "creative must NOT serve at a different pincode (same state)",
    ).toBe(false);
    expect(
      await servesOurOffer({ slot: "milk_home_hero", pincode: PINCODE, category: "milk" }),
      "creative must NOT serve for the wrong category",
    ).toBe(false);
    expect(
      await servesOurOffer({ slot: "milk_home_hero", category: "ghee" }), // no pincode at all
      "creative must NOT serve with no pincode context (fail-closed)",
    ).toBe(false);

    // --- 6. NN2 in e2e: replay is a no-op, tampered signature is rejected ---
    const replayRes = await fetch(`${API}/billing/webhook/razorpay`, {
      method: "POST",
      body: paidRaw,
      headers: paidHeaders,
    });
    expect(replayRes.status).toBe(200);
    expect((await replayRes.json()).status).toBe("duplicate");

    const tamperedBody = paidWebhookBody({
      plinkId,
      orderId: order.id,
      paymentId: "pay_e2e_tampered",
      amountPaise: totalPaise + 1, // amount tamper, on top of the bad signature below
    });
    const { raw: tamperedRaw, headers: tamperedHeaders } = signed(tamperedBody);
    tamperedHeaders["x-razorpay-signature"] = "deadbeef"; // stale/wrong signature
    const tamperedRes = await fetch(`${API}/billing/webhook/razorpay`, {
      method: "POST",
      body: tamperedRaw,
      headers: tamperedHeaders,
    });
    expect(tamperedRes.status).toBe(400);

    // --- 7. Advertiser stats reflect the served, targeted delivery ---------
    const statsRes = await advertiser.get(`/ads/my/campaigns/${campaignId}/stats?days=7`);
    expect(statsRes.ok()).toBeTruthy();
    const stats = (await statsRes.json()) as {
      serves_used: number;
      by_pincode: { key: string; serves: number }[];
    };
    expect(stats.serves_used).toBeGreaterThanOrEqual(1);
    expect(stats.by_pincode.some((row) => row.key === PINCODE)).toBeTruthy();

    await advertiser.dispose();
  });

  test("@matrix mobile wizard walk: goal -> categories -> areas are usable on a small screen", async ({
    page,
    browserName,
  }) => {
    test.skip(browserName === "webkit", WEBKIT_HTTP_COOKIE_SKIP);
    test.setTimeout(120_000);
    const phone = randomPhone();

    const assertNoHorizontalOverflow = async () => {
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1); // 1px rounding slack
    };
    const assertTappable = async (locator: Locator) => {
      const box = await locator.boundingBox();
      expect(box, "control has no layout box - not visible/tappable").toBeTruthy();
      expect(box!.height).toBeGreaterThanOrEqual(44); // D26/D29 min tap-target rule
    };

    await resetOtpThrottle(phone);
    await page.goto(`${AGRI}/business/ads`);
    await completeLoginUi(page, phone);
    await completeNewUserSteps(page);
    await page.waitForURL(new RegExp(`^${AGRI}/business/ads`), { timeout: 30_000 });

    await page.goto(`${AGRI}/business/listings`);
    await page.getByLabel("Business name").fill("E2E Mobile Advertiser Co");
    await page.getByLabel("Primary pincode").fill(PINCODE);
    await page.getByRole("button", { name: "Create listing" }).click();
    await expect(page.getByRole("combobox", { name: "Business", exact: true })).toBeVisible({
      timeout: 45_000, // cold-compile headroom, same reason as the NN1 walk above
    });

    await page.goto(`${AGRI}/business/ads`);
    await page.getByRole("button", { name: "New campaign" }).click();
    await assertNoHorizontalOverflow();

    // Goal
    const nameField = page.getByLabel("Campaign name");
    await nameField.fill("Mobile wizard check");
    await assertTappable(nameField);
    await page.getByRole("radio", { name: /banner ads/i }).click();
    // Checkboxes here are deliberately small (wizard-steps.tsx styles the
    // native <input> at 20px) - the WRAPPING <label> is the real 44px tap
    // target (native label/input association makes the whole label
    // clickable), so tappability is asserted on the label, not the input.
    const heroCheckbox = page.getByRole("checkbox", { name: /home page hero/i });
    await heroCheckbox.check();
    await assertTappable(heroCheckbox.locator("xpath=.."));
    await assertNoHorizontalOverflow();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    // Categories
    await page.getByRole("checkbox", { name: /all categories/i }).uncheck();
    const gheeCheckbox = page.getByRole("checkbox", { name: /^ghee$/i });
    await expect(gheeCheckbox).toBeVisible({ timeout: 15_000 });
    await gheeCheckbox.check();
    await assertTappable(gheeCheckbox.locator("xpath=.."));
    await assertNoHorizontalOverflow();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    // Areas
    const pincodesRadio = page.getByRole("radio", { name: /specific pincodes/i });
    await pincodesRadio.click();
    await page.getByPlaceholder("6-digit pincode").fill(PINCODE);
    const addButton = page.getByRole("button", { name: "Add", exact: true });
    await assertTappable(addButton);
    await addButton.click();
    await expect(page.getByText(PINCODE)).toBeVisible();
    await assertNoHorizontalOverflow();
  });
});
