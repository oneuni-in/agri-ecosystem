import { expect, test } from "@playwright/test";

// web-milk runs on :3000 but the Playwright baseURL is web-id (:3003),
// so every navigation here uses an absolute URL.
import { MILK, waitForHeaderSettled } from "./helpers";

/**
 * U4 A1 regression: a guest visit must log ZERO console errors — and the fix
 * contract is stronger than "no errors": the authenticated probes must never
 * be MADE for a visitor without a session hint (swallowing the 401s instead
 * would keep the console clean by muffling real failures, which is the
 * anti-pattern U4 explicitly bans). The silent-SSO bounce is allowed: every
 * request it makes is a 2xx/302 (helpers.ts documents the dance).
 */
test.describe("U4 A1 — guest console hygiene", () => {
  test("guest navigation: zero console errors, zero 401s, zero authed probes", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    const unauthorized: string[] = [];
    const authedProbes: string[] = [];
    page.on("console", (msg) => {
      // One scoped, documented exclusion — NOT a muffle of the 401s this row
      // is about: React's dev-only hydration-mismatch warning ("A tree
      // hydrated but…") fires today because AdUnit branches target/rel on
      // `typeof window` (ad-slot.tsx, pre-existing, logged as a U4 finding in
      // polish-u1.md §9.4). Production hydration performs no attribute
      // comparison, so the acceptance run — production build — never sees it;
      // this suite runs `next dev`, which does. Everything else stays zero.
      if (msg.type() === "error" && !msg.text().startsWith("A tree hydrated but")) {
        consoleErrors.push(msg.text());
      }
    });
    page.on("response", (res) => {
      if (res.status() === 401) unauthorized.push(res.url());
    });
    page.on("request", (req) => {
      if (/\/api\/auth\/me|\/api\/coins\/balance|\/api\/notify\//.test(req.url())) {
        authedProbes.push(req.url());
      }
    });
    // Home, results, category, search — the guest surfaces A1 was run on.
    for (const path of ["/", "/coimbatore/641001", "/p/ghee", "/search?q=milk"]) {
      await page.goto(`${MILK}${path}`);
      await waitForHeaderSettled(page);
    }
    expect(authedProbes).toEqual([]);
    expect(unauthorized).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});

test.describe("D23 milk pincode home — three empty-state branches", () => {
  test("(a) covered TN pincode with a seeded vendor shows results", async ({ page }) => {
    await page.goto(`${MILK}/641001`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("scope-covered")).toBeVisible();
    await expect(page.getByTestId("type-filter-row")).toBeVisible();
    // U1b: the results page renders the §5b PriceTicker marquee (the same
    // catalog composite as the home) in place of the old dashed price box.
    await expect(page.getByTestId("price-ticker")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Local vendors/i })).toBeVisible();
  });

  test("(b) valid TN pincode with no vendors shows the warm district state + notify-me", async ({
    page,
  }) => {
    // 600001 (Chennai) is a real TN pincode in the geo fixture with no
    // business coverage — the seed only covers 641001 (Coimbatore).
    await page.goto(`${MILK}/600001`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("scope-tn-no-vendors")).toBeVisible();
    await expect(page.getByText(/No milk vendors in/i)).toBeVisible();
    await expect(page.getByTestId("notify-me")).toBeVisible();
  });

  test("(c) non-TN pincode shows the out-of-area state + notify-me", async ({ page }) => {
    // 110001 (Delhi) is not present in the geo fixture at all.
    await page.goto(`${MILK}/110001`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("scope-out-of-area")).toBeVisible();
    await expect(page.getByText(/live in Tamil Nadu/i)).toBeVisible();
    await expect(page.getByTestId("notify-me")).toBeVisible();
  });

  test("notify-me submits from the out-of-area state", async ({ page }) => {
    await page.goto(`${MILK}/110001`);
    await waitForHeaderSettled(page); // let the silent-SSO bounce finish before we click
    await page.getByRole("button", { name: /notify me/i }).click();
    await expect(page.getByTestId("notify-done")).toBeVisible();
  });
});
