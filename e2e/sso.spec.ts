/**
 * D10.E: one login works across TLD stand-ins (localhost multi-port); prod
 * uses real domains per packages/auth-client/README.md. web-admin's role
 * gate is covered by auth-client unit tests, not a fifth dev server.
 */
import { expect, test } from "@playwright/test";

import { completeLoginUi, randomPhone, resetOtpThrottle } from "./helpers";

const MILK = "http://localhost:3000";
const ORGANIC = "http://localhost:3001";
const ID = "http://localhost:3003";

test("login once on milk -> in on organic -> logout-everywhere kills both", async ({ page }) => {
  const phone = randomPhone();
  await resetOtpThrottle(phone);

  // ---- login on milk via the header Login button (full BFF journey)
  await page.goto(MILK);
  await page.getByRole("button", { name: /^login$/i }).click();
  await page.waitForURL(`${ID}/login**`);
  await completeLoginUi(page, phone);
  // fresh phone => new user: the login-flow UI runs handle + language steps
  // before it resumes the pending /authorize and redirects back to milk.
  await page.getByRole("button", { name: /skip/i }).click();
  await page.getByRole("button", { name: /english/i }).click();
  await page.waitForURL(`${MILK}/**`);
  await expect(page.getByRole("button", { name: /🪙/ })).toBeVisible();

  // ---- NON-NEGOTIABLE 1: no tokens anywhere JS can reach
  const jsVisible = await page.evaluate(() => ({
    local: JSON.stringify(localStorage),
    session: JSON.stringify(sessionStorage),
    cookies: document.cookie,
  }));
  for (const surface of Object.values(jsVisible)) {
    expect(surface).not.toMatch(/eyJ[\w-]{10,}/); // JWT/JWE shape
  }
  const cookies = await page.context().cookies(MILK);
  const sessionCookie = cookies.find((c) => c.name === "milk_session");
  expect(sessionCookie).toBeTruthy();
  expect(sessionCookie!.httpOnly).toBe(true);

  // ---- visit organic: silent SSO, no login UI, no OTP
  await page.goto(ORGANIC);
  await expect(page.getByRole("button", { name: /🪙/ })).toBeVisible({ timeout: 20_000 });
  expect(page.url().startsWith(ORGANIC)).toBe(true); // never parked on a login screen

  // ---- NON-NEGOTIABLE 1 again: silent SSO must not leak tokens either
  const organicJsVisible = await page.evaluate(() => ({
    local: JSON.stringify(localStorage),
    session: JSON.stringify(sessionStorage),
    cookies: document.cookie,
  }));
  for (const surface of Object.values(organicJsVisible)) {
    expect(surface).not.toMatch(/eyJ[\w-]{10,}/); // JWT/JWE shape
  }
  const organicCookies = await page.context().cookies(ORGANIC);
  const organicSessionCookie = organicCookies.find((c) => c.name === "organic_session");
  expect(organicSessionCookie).toBeTruthy();
  expect(organicSessionCookie!.httpOnly).toBe(true);

  // ---- logout-everywhere on id.agri.in (devices manager)
  await page.goto(`${ID}/devices`);
  await page.getByRole("button", { name: /sign out everywhere/i }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /sign out everywhere/i })
    .click();
  await expect(page).toHaveURL(/\/login/); // logoutEverywhere() redirects the current tab itself

  // ---- both apps are logged out (back-channel + failed silent re-auth)
  await page.goto(MILK);
  await expect(page.getByRole("button", { name: /^login$/i })).toBeVisible({ timeout: 20_000 });
  await page.goto(ORGANIC);
  await expect(page.getByRole("button", { name: /^login$/i })).toBeVisible({ timeout: 20_000 });
});

test("silent SSO probe fails gracefully for a fresh visitor", async ({ page }) => {
  await page.goto(ORGANIC);
  // the tab auto-probes prompt=none once, comes back unauthenticated, no UI trap
  await expect(page.getByRole("button", { name: /^login$/i })).toBeVisible({ timeout: 20_000 });
  expect(page.url().startsWith(ORGANIC)).toBe(true);
});
