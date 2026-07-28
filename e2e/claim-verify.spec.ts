import { expect, test } from "@playwright/test";

import {
  AGRI,
  API,
  WEBKIT_HTTP_COOKIE_SKIP,
  completeLoginUi,
  completeNewUserSteps,
  randomPhone,
  staffApi,
} from "./helpers";

const CLAIMABLE_SLUG = "e2e-claimable-dairy"; // seed_e2e_milk.py, NULL owner

type AdminClaim = { id: string; business_id: string; status: string };

/**
 * Deliberately NOT tagged `@matrix`, i.e. desktop only.
 *
 * The journey consumes a one-shot fixture: approving the claim sets an owner,
 * and "E2E Claimable Dairy" is a single row, so a second project running the
 * same journey in the same suite finds it already claimed. Only re-running
 * seed_e2e_milk.py resets it. Rather than seed a business per project, or
 * weaken the test to tolerate an owned fixture (which would stop proving the
 * approval did anything), the journey runs once end to end.
 *
 * Device coverage is not really lost: the claim form is a plain file input and
 * submit button on web-agri, and D29's tap-target and locale sweeps already
 * exercise responsive rendering.
 */
test.describe("D29 claim → verify (D16)", () => {
  test.skip(({ browserName }) => browserName === "webkit", WEBKIT_HTTP_COOKIE_SKIP);

  test("user claims an unowned listing, staff approves, the listing stops being claimable", async ({
    page,
    request,
  }) => {
    // The fixture is reset to NULL-owner by seed_e2e_milk.py, so a previous
    // run's approval does not make this unrepeatable.
    const detail = await request.get(`${API}/directory/businesses/${CLAIMABLE_SLUG}`);
    expect(detail.ok(), `${CLAIMABLE_SLUG} missing - run seed_e2e_milk.py`).toBeTruthy();
    const business = ((await detail.json()) as { business: { id: string; claimable: boolean } })
      .business;
    expect(business.claimable, "fixture is already owned - re-run seed_e2e_milk.py").toBeTruthy();

    const staff = await staffApi();
    const queued = async (): Promise<AdminClaim[]> => {
      const res = await staff.get("/admin/directory/claims?status=pending&limit=100");
      expect(res.ok()).toBeTruthy();
      return ((await res.json()) as { items: AdminClaim[] }).items;
    };
    const before = new Set((await queued()).map((c) => c.id));

    // --- file the claim in web-agri (the claim UI lives there, not web-milk).
    //     The page server-redirects guests straight into the login flow. ---
    const phone = randomPhone();
    await page.goto(`${AGRI}/directory/businesses/${CLAIMABLE_SLUG}/claim`);
    await completeLoginUi(page, phone);
    await completeNewUserSteps(page);
    await expect(page.getByRole("heading", { name: /claim /i })).toBeVisible({ timeout: 30_000 });
    // Let dev-JIT finish shipping the island's chunks. Clicking Submit before
    // React attaches performs a NATIVE form submit, which reloads the page and
    // silently drops the chosen file - the form simply reappears pristine with
    // no error to explain itself.
    await page.waitForLoadState("networkidle");

    // Target the real <input type=file>: the label wraps it, so getByLabel
    // resolves to the styled control in the a11y tree, not the input itself.
    await page.locator('input[type="file"]').setInputFiles("e2e/fixtures/evidence.png");
    await page.getByRole("button", { name: /submit claim/i }).click();
    await expect(page.getByText(/claim submitted/i)).toBeVisible({ timeout: 30_000 });

    // --- staff approves THIS claim (diffed, not "the first pending one") ---
    const mine = (await queued()).find((c) => !before.has(c.id) && c.business_id === business.id);
    expect(mine, "the submitted claim never reached the pending queue").toBeTruthy();
    const approved = await staff.post(`/admin/directory/claims/${mine!.id}/approve`, {
      data: { note: "d29 e2e" },
    });
    expect(approved.status()).toBe(200);
    await staff.dispose();

    // --- ownership took effect: the listing is no longer claimable ---
    const after = await request.get(`${API}/directory/businesses/${CLAIMABLE_SLUG}`);
    expect(((await after.json()) as { business: { claimable: boolean } }).business.claimable).toBe(
      false,
    );
    await page.reload();
    await expect(page.getByText(/already claimed/i)).toBeVisible({ timeout: 30_000 });
  });
});
