import { expect, test } from "@playwright/test";

import { errorAlert, fillOtp, loginAs, peekOtp, randomPhone, resetOtpThrottle } from "./helpers";

test.describe("D09 auth flows", () => {
  test("new-user signup: phone -> otp -> handle -> language -> devices", async ({ page }) => {
    const phone = randomPhone();
    await loginAs(page, phone);

    // new user lands on the handle picker
    await expect(page.getByText(/pick your @handle/i)).toBeVisible();
    const handle = `e2e_${phone.slice(4)}`;
    await page.getByPlaceholder("your_handle").fill(handle);
    await expect(page.getByText(/^available$/i)).toBeVisible();
    await page.getByRole("button", { name: /save handle/i }).click();

    // language picker, then devices
    await page.getByRole("button", { name: /tamil/i }).click();
    await expect(page).toHaveURL(/\/devices/);
    await expect(page.getByText(`@${handle}`)).toBeVisible();
    await expect(page.getByText(/this device|இந்த சாதனம்/i)).toBeVisible();
  });

  test("returning login skips handle and language", async ({ page }) => {
    const phone = randomPhone();
    await loginAs(page, phone); // first signup
    await page.getByRole("button", { name: /skip/i }).click();
    await page.getByRole("button", { name: /english/i }).click();
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
    await expect(page.getByText(/6-digit code/i)).toBeVisible();
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
