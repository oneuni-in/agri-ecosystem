/**
 * D28 push channel — real-browser verification (launch blocker #2:
 * "web push has never completed a real subscription").
 *
 * NOT part of the CI suite: headless/bundled Chromium has no FCM channel, so
 * pushManager.subscribe() can never complete there. This spec is the
 * executable form of docs/runbooks/web-push.md §verify — run it locally:
 *
 *   PUSH_VERIFY=1 npx playwright test e2e/push-verification.spec.ts \
 *     --config e2e/playwright.config.ts --project=desktop
 *
 * Requirements: real Chrome installed, network access to FCM, VAPID keys in
 * backend/core/.env + NEXT_PUBLIC_VAPID_PUBLIC_KEY in apps/web-milk/.env.local,
 * notify.push_enabled flag on, dev postgres container up (DB assertions use
 * docker exec psql).
 *
 * Proves, end to end:
 *  1. pushManager.subscribe() completes against the real push service and a
 *     row lands in notify.push_subscriptions (the row that had never existed).
 *  2. A real lead.responded event (vendor answers this user's inquiry) flows
 *     bus -> notify worker -> pywebpush -> FCM -> service worker, and the
 *     notification is DISPLAYED (asserted via registration.getNotifications()).
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { chromium, expect, test } from "@playwright/test";

import {
  API,
  MILK,
  VENDOR_PHONE,
  apiAs,
  completeLoginUi,
  completeNewUserSteps,
  fixtureSlug,
  randomPhone,
} from "./helpers";

function sql(query: string): string {
  // execFileSync + argv array: no shell, no interpolation surface.
  return execFileSync("docker", [
    "exec",
    "agri-dev-postgres-1",
    "psql",
    "-U",
    "app",
    "-d",
    "agri",
    "-tAc",
    query,
  ])
    .toString()
    .trim();
}

test.describe("D28 push — real browser, real FCM", () => {
  test.skip(
    !process.env.PUSH_VERIFY,
    "manual verification: run with PUSH_VERIFY=1 (real Chrome + FCM; not CI-runnable)",
  );

  test("subscribe persists a row and a lead.responded push is displayed", async () => {
    test.setTimeout(240_000);
    // Bundled Chromium has no push-service credentials — real Chrome only.
    // And it must be a PERSISTENT context: every browser.newContext() is an
    // incognito profile, and Chrome deliberately disables the Push API in
    // incognito (crbug.com/41124656) — subscribe() aborts with a misleading
    // "permission denied" there. This cost the first verification run.
    const context = await chromium.launchPersistentContext(
      mkdtempSync(join(tmpdir(), "push-verify-")),
      { channel: "chrome", headless: false },
    );
    await context.grantPermissions(["notifications"], { origin: MILK });
    const page = context.pages()[0] ?? (await context.newPage());

    try {
      // --- fresh user logs in on milk (BFF authorize dance -> /notifications)
      const phone = randomPhone();
      await page.goto(`${MILK}/api/auth/login?next=%2Fnotifications`);
      await completeLoginUi(page, phone);
      await completeNewUserSteps(page);
      await expect(page).toHaveURL(/\/notifications/, { timeout: 30_000 });

      // --- subscribe: the real browser <-> push-service handshake ---
      const card = page.getByTestId("push-alerts-card");
      await expect(card).toBeVisible({ timeout: 15_000 });
      const [subscribeResponse] = await Promise.all([
        page.waitForResponse(
          (r) =>
            r.url().includes("/api/notify/push/subscriptions") &&
            r.request().method() === "POST",
          { timeout: 60_000 },
        ),
        card.getByRole("button", { name: /turn on/i }).click(),
      ]);
      expect(subscribeResponse.status()).toBe(200);
      await expect(card.getByRole("button", { name: /turn off/i })).toBeVisible({
        timeout: 15_000,
      });

      // --- the row that had never existed (launch blocker #2) ---
      const endpoint = sql(
        "SELECT endpoint FROM notify.push_subscriptions ORDER BY created_at DESC LIMIT 1",
      );
      expect(endpoint, "no push_subscriptions row landed").toMatch(/^https:\/\//);

      // --- real trigger: this user asks, the vendor answers ---
      // (randomPhone() is bare 10-digit for the login UI; apiAs wants E.164)
      const me = await apiAs(`+91${phone}`);
      const slug = await fixtureSlug(me);
      const bizRes = await me.get(`${API}/directory/businesses/${slug}`);
      expect(bizRes.ok()).toBeTruthy();
      const businessId = ((await bizRes.json()) as { business: { id: string } }).business.id;

      const inquiry = await me.post("/leads/inquiries", {
        data: {
          type: "contact",
          business_id: businessId,
          pincode: "641001",
          payload: { message: "Push verification inquiry - do you deliver?" },
        },
      });
      expect(inquiry.ok()).toBeTruthy();
      const inquiryId = ((await inquiry.json()) as { id: string }).id;

      const vendor = await apiAs(VENDOR_PHONE);
      const responded = await vendor.post(`/leads/inquiries/${inquiryId}/responses`, {
        data: { body: "Yes - we deliver tomorrow morning." },
      });
      expect(responded.ok()).toBeTruthy();

      // --- server side: the push delivery row goes sent (worker consumed the
      //     bus event, pywebpush accepted by FCM) ---
      await expect
        .poll(
          () =>
            sql(
              "SELECT count(*) FROM notify.deliveries d " +
                "JOIN notify.notifications n ON n.id = d.notification_id " +
                "WHERE d.channel = 'push' AND d.status = 'sent' " +
                "AND n.template_key = 'lead_response'",
            ),
          { timeout: 60_000, intervals: [2_000] },
        )
        .not.toBe("0");

      // --- browser side: the service worker actually DISPLAYED it ---
      // (evaluate is retried through next-dev HMR full reloads, which destroy
      // the execution context mid-poll — same hazard the CLS spec documents)
      await expect
        .poll(
          async () => {
            try {
              return await page.evaluate(async () => {
                const registration = await navigator.serviceWorker.ready;
                const shown = await registration.getNotifications();
                return shown.length;
              });
            } catch {
              return 0; // context destroyed by a dev reload - poll again
            }
          },
          { timeout: 60_000, intervals: [2_000] },
        )
        .toBeGreaterThan(0);

      await me.dispose();
      await vendor.dispose();
    } finally {
      await context.close();
    }
  });
});
