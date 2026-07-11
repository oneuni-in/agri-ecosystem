import { expect, type Page } from "@playwright/test";

export const API = "http://127.0.0.1:8000";

export function randomPhone(): string {
  // 10-digit Indian mobile, 9-prefix; uniqueness per run keeps scenarios independent
  return `9${Math.floor(100_000_000 + Math.random() * 899_999_999)}`;
}

export async function resetOtpThrottle(phone: string): Promise<void> {
  await fetch(`${API}/auth/otp/_reset`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ phone }),
  });
}

export async function peekOtp(phone: string): Promise<string> {
  const response = await fetch(`${API}/auth/otp/_peek?phone=${encodeURIComponent(phone)}`);
  const body = (await response.json()) as { code: string | null };
  if (!body.code) throw new Error(`no OTP recorded for ${phone}`);
  return body.code;
}

export async function fillOtp(page: Page, code: string): Promise<void> {
  // typing into box 1 with auto-advance covers the component contract
  const first = page.getByRole("textbox", { name: /1\/6/ });
  await first.click();
  await page.keyboard.type(code, { delay: 40 });
}

export async function loginAs(page: Page, phone: string): Promise<void> {
  await resetOtpThrottle(phone); // same-phone re-login must not wait out the 30s cooldown
  await page.goto("/login");
  await page.getByLabel(/mobile number/i).fill(phone);
  await page.getByRole("button", { name: /send otp/i }).click();
  await expect(page.getByText(/6-digit code/i)).toBeVisible();
  await fillOtp(page, await peekOtp(`+91${phone}`));
}

/** The app's own error line - Next's route announcer also carries role=alert. */
export function errorAlert(page: Page) {
  return page.locator("p[role='alert']");
}
