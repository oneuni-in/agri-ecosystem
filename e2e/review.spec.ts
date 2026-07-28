import { expect, test } from "@playwright/test";

import {
  API,
  MILK,
  WEBKIT_HTTP_COOKIE_SKIP,
  completeLoginUi,
  completeNewUserSteps,
  fixtureSlug,
  randomPhone,
  staffApi,
  waitForHeaderSettled,
} from "./helpers";

type Review = { id: string; body?: { en?: string } | null; moderation_status?: string };

test.describe("D29 review round-trip (D18)", { tag: "@matrix" }, () => {
  test.skip(({ browserName }) => browserName === "webkit", WEBKIT_HTTP_COOKIE_SKIP);

  test("a review posts as pending, stays hidden, and appears once staff approves", async ({
    page,
    request,
  }) => {
    const slug = await fixtureSlug(request);
    const detail = await request.get(`${API}/directory/businesses/${slug}`);
    expect(detail.ok()).toBeTruthy();
    const businessId = ((await detail.json()) as { business: { id: string } }).business.id;

    // Unique body text: this is what identifies THIS run's review in queues
    // that accumulate rows locally.
    const bodyText = `Fresh and on time every morning ${randomPhone()}`;

    const publicReviews = async (): Promise<Review[]> => {
      const res = await request.get(
        `${API}/reviews?target_type=business&target_id=${businessId}&limit=100`,
      );
      expect(res.ok()).toBeTruthy();
      return ((await res.json()) as { items: Review[] }).items;
    };
    const summaryCount = async (): Promise<number> => {
      const res = await request.get(
        `${API}/reviews/summary?target_type=business&target_id=${businessId}`,
      );
      expect(res.ok()).toBeTruthy();
      return ((await res.json()) as { rating_count: number }).rating_count;
    };
    const countBefore = await summaryCount();

    // --- log in, then post the review from the business page ---
    const phone = randomPhone();
    await page.goto(`${MILK}/directory/businesses/${slug}`);
    await waitForHeaderSettled(page);
    await page.getByRole("link", { name: /login to write a review/i }).click();
    await completeLoginUi(page, phone);
    await completeNewUserSteps(page);
    await expect(page).toHaveURL(new RegExp(`/directory/businesses/${slug}`), { timeout: 30_000 });
    // hydration: an early click submits the form natively and loses the input
    await page.waitForLoadState("networkidle");

    // The star radios are `sr-only` (the visible <label> carries the 44px
    // target via the `peer` pattern), so .check() can never land a click on
    // them - click the label, which is what a user actually taps.
    await page.locator('label[for="review-rating-5"]').click();
    await expect(page.getByRole("radio", { name: "Rate 5 of 5" })).toBeChecked();
    await page.getByLabel(/review \(optional\)/i).fill(bodyText);
    await page.getByRole("button", { name: /submit review/i }).click();
    await expect(page.getByText(/visible after moderation/i)).toBeVisible({ timeout: 30_000 });

    // --- pending means NOT public, and the aggregate has not moved ---
    expect((await publicReviews()).some((r) => r.body?.en === bodyText)).toBeFalsy();
    expect(await summaryCount()).toBe(countBefore);

    // --- staff approves THIS review ---
    const staff = await staffApi();
    const queue = await staff.get("/admin/reviews?status=pending&limit=100");
    expect(queue.ok()).toBeTruthy();
    const mine = ((await queue.json()) as { items: Review[] }).items.find(
      (r) => r.body?.en === bodyText,
    );
    expect(mine, "the submitted review never reached the moderation queue").toBeTruthy();
    const approved = await staff.post(`/admin/reviews/${mine!.id}/approve`);
    expect(approved.status()).toBe(200);
    await staff.dispose();

    // --- now public, and the aggregate counted it ---
    expect((await publicReviews()).some((r) => r.body?.en === bodyText)).toBeTruthy();
    expect(await summaryCount()).toBe(countBefore + 1);
  });
});
