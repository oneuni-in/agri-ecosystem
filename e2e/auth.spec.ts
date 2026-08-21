import { expect, test } from "@playwright/test";

import {
  continuePastDoneScreen,
  errorAlert,
  fillOtp,
  loginAs,
  peekOtp,
  randomPhone,
  resetOtpThrottle,
} from "./helpers";

test.describe("D09 auth flows", () => {
  test("new-user signup: phone -> otp -> handle -> language -> devices", async ({ page }) => {
    const phone = randomPhone();
    await loginAs(page, phone);

    // new user lands on the handle picker
    await expect(page.getByText(/pick your @handle/i)).toBeVisible();
    const handle = `e2e_${phone.slice(4)}`;
    await page.getByPlaceholder("your_handle").fill(handle);
    // ID-U1 P3 made every handle verdict name the handle it is about
    // ("@e2e_1234 is available"), so the old exact match on "Available" no
    // longer applies. Asserting the status line's CONTENT is also stronger:
    // it proves the verdict is about the handle just typed.
    await expect(page.locator("p[role='status']")).toContainText(
      new RegExp(`@${handle} is available`, "i"),
    );
    await page.getByRole("button", { name: /save handle/i }).click();

    // language picker, then devices
    await page.getByRole("button", { name: /tamil/i }).click();
    await continuePastDoneScreen(page);
    // 20s, not the 5s default: this is the suite's FIRST navigation to
    // /devices, and under dev-JIT that means compiling the route on demand.
    // A local trace of the 5s failure shows POST /auth/language -> 200 and
    // the push issued - the page was simply still compiling. Same class as
    // completeLoginUi's hydration allowance.
    await expect(page).toHaveURL(/\/devices/, { timeout: 20_000 });
    await expect(page.getByText(`@${handle}`)).toBeVisible();
    await expect(page.getByText(/this device|இந்த சாதனம்/i)).toBeVisible();
  });

  test("ID-U1 P5: a new signup gets the done screen; a returning login does not", async ({
    page,
  }) => {
    const phone = randomPhone();
    await loginAs(page, phone);
    await page.getByRole("button", { name: /skip/i }).click();
    await page.getByRole("button", { name: /english/i }).click();

    // the screen the flow used to skip silently
    await expect(page.getByText(/your agriid is ready/i)).toBeVisible();
    // the coins line comes from the rules table, so assert the SHAPE rather
    // than a literal - a hardcoded 100 here would defeat the point of reading
    // the amount at render time
    await expect(page.getByText(/\+\d+\s+AgriCoins/i)).toBeVisible();
    // and it still performs the redirect the flow always performed
    await continuePastDoneScreen(page);
    await expect(page).toHaveURL(/\/devices/);

    // returning: straight through, no interstitial on every sign-in
    await page.getByRole("button", { name: /^sign out$/i }).first().click();
    await expect(page).toHaveURL(/\/login/);
    await loginAs(page, phone);
    await expect(page).toHaveURL(/\/devices/);
    await expect(page.getByText(/your agriid is ready/i)).toHaveCount(0);
  });

  test("returning login skips handle and language", async ({ page }) => {
    const phone = randomPhone();
    await loginAs(page, phone); // first signup
    await page.getByRole("button", { name: /skip/i }).click();
    await page.getByRole("button", { name: /english/i }).click();
    await continuePastDoneScreen(page);
    await expect(page).toHaveURL(/\/devices/);
    await page.getByRole("button", { name: /^sign out$/i }).first().click();
    await expect(page).toHaveURL(/\/login/);

    await loginAs(page, phone); // returning
    await expect(page).toHaveURL(/\/devices/); // straight through
  });

  test("wrong OTP shows error, then lockout UX after burn", async ({ page }) => {
    const phone = randomPhone();
    await resetOtpThrottle(phone);
    await page.goto("/login");
    await page.getByLabel(/mobile number/i).fill(phone);
    await page.getByRole("button", { name: /send otp/i }).click();
    await expect(page.getByText(/6-digit (code|OTP)/i)).toBeVisible();
    const real = await peekOtp(`+91${phone}`);
    const wrong = real === "000000" ? "111111" : "000000";

    for (let attempt = 0; attempt < 3; attempt += 1) {
      await fillOtp(page, wrong);
      await expect(errorAlert(page)).toBeVisible(); // wrong-code message
      // boxes clear after every failed verify - proves the round-trip landed
      await expect(page.getByRole("textbox", { name: /1\/6/ })).toHaveValue("");
    }
    // OTP_MAX_ATTEMPTS = 3: the code is burned - even the real one fails now
    await fillOtp(page, real);
    await expect(errorAlert(page)).toBeVisible();
    // resend is the recovery path and shows its cooldown countdown
    await expect(page.getByRole("button", { name: /resend/i })).toBeVisible();
  });

  test("device revoke signs the other browser out", async ({ browser }) => {
    const phone = randomPhone();
    const deviceA = await browser.newContext();
    const deviceB = await browser.newContext({ userAgent: "e2e-second-device" });
    const pageA = await deviceA.newPage();
    const pageB = await deviceB.newPage();

    await loginAs(pageA, phone);
    await pageA.getByRole("button", { name: /skip/i }).click();
    await pageA.getByRole("button", { name: /english/i }).click();
    await continuePastDoneScreen(pageA);
    await expect(pageA).toHaveURL(/\/devices/);
    await loginAs(pageB, phone);
    await expect(pageB).toHaveURL(/\/devices/);

    // A revokes B (the non-current row)
    await pageA.goto("/devices");
    const otherRow = pageA
      .getByTestId("device-list")
      .locator("li")
      .filter({ hasNot: pageA.getByText(/this device/i) })
      .first();
    await otherRow.getByRole("button", { name: /^sign out$/i }).click();
    await pageA
      .getByRole("dialog")
      .getByRole("button", { name: /^sign out$/i })
      .click();

    await pageB.reload();
    await expect(pageB).toHaveURL(/\/login/); // server-side session store said no
    await deviceA.close();
    await deviceB.close();
  });

  test("logout-everywhere kills both devices at once", async ({ browser }) => {
    const phone = randomPhone();
    const deviceA = await browser.newContext();
    const deviceB = await browser.newContext({ userAgent: "e2e-second-device" });
    const pageA = await deviceA.newPage();
    const pageB = await deviceB.newPage();

    await loginAs(pageA, phone);
    await pageA.getByRole("button", { name: /skip/i }).click();
    await pageA.getByRole("button", { name: /english/i }).click();
    await continuePastDoneScreen(pageA);
    await expect(pageA).toHaveURL(/\/devices/);
    await loginAs(pageB, phone);
    await expect(pageB).toHaveURL(/\/devices/);

    await pageA.goto("/devices");
    await pageA.getByRole("button", { name: /sign out everywhere/i }).click();
    await pageA
      .getByRole("dialog")
      .getByRole("button", { name: /sign out everywhere/i })
      .click();
    await expect(pageA).toHaveURL(/\/login/);

    await pageB.reload();
    await expect(pageB).toHaveURL(/\/login/);
    await deviceA.close();
    await deviceB.close();
  });
});
