import { expect, request, type APIRequestContext, type Page } from "@playwright/test";

export const API = "http://127.0.0.1:8000";
export const MILK = "http://localhost:3000";
export const AGRI = "http://localhost:3002";
/** seed_e2e_milk.py: holds the `staff` role, for D29's moderation steps. */
export const STAFF_PHONE = "+919000000029";
/** seed_e2e_milk.py: owns "E2E Milk Vendor". */
export const VENDOR_PHONE = "+919000000023";

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

/** Complete the web-id login UI when we ARRIVED there via a redirect (the
 * BFF authorize dance), unlike loginAs which starts at /login itself. */
export async function completeLoginUi(page: Page, phone: string): Promise<void> {
  const input = page.getByLabel(/mobile number/i);
  const send = page.getByRole("button", { name: /send otp/i });
  // Hydration-resilient fill: when a spec is the first to touch /login, dev-JIT
  // can hydrate the island AFTER the first fill. The typed value then never
  // reaches React state and Send OTP stays SSR-disabled forever. Refilling
  // until the button reacts proves hydration has attached.
  await input.waitFor({ timeout: 30_000 });
  await expect(async () => {
    await input.fill("");
    await input.fill(phone);
    await expect(send).toBeEnabled({ timeout: 2_000 });
  }).toPass({ timeout: 30_000 });
  await send.click();
  await expect(page.getByText(/6-digit code/i)).toBeVisible();
  await fillOtp(page, await peekOtp(`+91${phone}`));
}

/** Progressive-account tail for a phone that has never logged in: skip the
 * handle step, pick a language, which finish()es into the authorize resume. */
export async function completeNewUserSteps(page: Page): Promise<void> {
  await page.getByRole("button", { name: /skip for now/i }).click({ timeout: 20_000 });
  await page.getByRole("button", { name: /english/i }).click({ timeout: 20_000 });
}

export async function loginAs(page: Page, phone: string): Promise<void> {
  await resetOtpThrottle(phone); // same-phone re-login must not wait out the 30s cooldown
  await page.goto("/login");
  await completeLoginUi(page, phone);
}

/** The app's own error line - Next's route announcer also carries role=alert. */
export function errorAlert(page: Page) {
  return page.locator("p[role='alert']");
}

/**
 * Cookie-authenticated API context for a seeded phone: the same OTP ->
 * /auth/login progressive flow the browser uses, driven over HTTP.
 *
 * Requires the API to be running with OTP_TEST_PEEK (scripts/e2e-api.mjs sets
 * it). If a dockerised API already holds :8000 Playwright reuses it, the peek
 * routes 404, and every caller fails with "no OTP recorded" - stop that
 * container rather than reaching for a different auth path.
 */
export async function apiAs(phone: string): Promise<APIRequestContext> {
  const bootstrap = await request.newContext({ baseURL: API });
  await resetOtpThrottle(phone);
  const requested = await bootstrap.post("/auth/otp/request", {
    data: { phone, purpose: "login" },
  });
  expect(requested.ok()).toBeTruthy();
  const code = await peekOtp(phone);
  const verify = await bootstrap.post("/auth/otp/verify", {
    data: { phone, purpose: "login", code },
  });
  expect(verify.ok()).toBeTruthy();
  const { otp_proof } = (await verify.json()) as { otp_proof: string };
  const login = await bootstrap.post("/auth/login", { data: { otp_proof } });
  expect(login.ok()).toBeTruthy();
  // agri_sid is Secure; the request-context jar won't replay it over plain
  // http://127.0.0.1, so carry it as an explicit header instead.
  const state = await bootstrap.storageState();
  const sid = state.cookies.find((c) => c.name === "agri_sid")?.value;
  expect(sid).toBeTruthy();
  await bootstrap.dispose();
  return request.newContext({
    baseURL: API,
    extraHTTPHeaders: { cookie: `agri_sid=${sid}` },
  });
}

/** Staff-role API context for the D29 moderation steps. */
export function staffApi(): Promise<APIRequestContext> {
  return apiAs(STAFF_PHONE);
}

/**
 * Why logged-in journeys cannot run on the mobile-safari project (D29).
 *
 * The session cookie `agri_sid` is `Secure`, and the local dev servers speak
 * plain http. Chromium treats http://localhost as a trustworthy origin and
 * sends Secure cookies to it anyway; WebKit does not - it stores the cookie
 * but never sends it, so /api/auth/me answers 401 {"user":null} forever. The
 * OTP itself is fine (verify returns 200 with a valid otp_proof and
 * /auth/login returns status:ok); only the browser's follow-up requests are
 * anonymous, which surfaces as the login screen claiming the code was wrong.
 *
 * This is a limitation of an http test rig, NOT a product defect: production
 * is https, where Safari sends the cookie normally. Verifying iOS Safari
 * end-to-end therefore needs a run against the https staging origin, and that
 * is recorded as an owner-run item in docs/qa/d29-device-matrix.md.
 */
export const WEBKIT_HTTP_COOKIE_SKIP =
  "logged-in journeys need https on WebKit: it will not send the Secure agri_sid cookie over http://localhost (see helpers.ts)";

/**
 * Every page load races the header's `AuthCluster` silent-SSO probe (D10): a
 * fresh, cookie-less visitor bounces through `/api/auth/login?silent=1` and
 * back before settling. Interacting before that round trip resolves can hit a
 * page mid-navigation and lose client state (e.g. a form's in-progress submit),
 * so wait for the header to settle on its logged-out "Login" button first.
 */
export async function waitForHeaderSettled(page: Page): Promise<void> {
  // By test id, not by accessible name: the label is translated, so the
  // original /^login$/i match could never settle on /ta or /hi and every
  // localised test timed out in the helper rather than on its own assertion.
  // 45s, not 20: WebKit takes ~10s of /api/auth/me churn to settle even on an
  // idle box, and on a runner already driving three dev servers late in a
  // suite that stretches past 20 (same rationale as the SW-install waits).
  await expect(page.getByTestId("auth-login")).toBeVisible({ timeout: 45_000 });
}

/** Resolve the seeded fixture's slug from the live API. BY SLUG, never by
 * position: milk_home orders by distance from the pincode centroid, so
 * `vendors[0]` is a D27 demo listing locally and the fixture only in CI. */
export async function fixtureSlug(ctx: APIRequestContext): Promise<string> {
  const res = await ctx.get(`${API}/catalog/milk/home/641001`);
  expect(res.ok()).toBeTruthy();
  const data = (await res.json()) as { vendors: { slug: string }[] };
  const fixture = data.vendors.find((v) => v.slug === "e2e-milk-vendor");
  expect(fixture, "seed fixture missing - run seed_e2e_milk.py").toBeTruthy();
  return fixture!.slug;
}
