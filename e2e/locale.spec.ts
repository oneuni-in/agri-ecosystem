import { expect, test, type Page } from "@playwright/test";

import {
  MILK,
  WEBKIT_HTTP_COOKIE_SKIP,
  completeLoginUi,
  completeNewUserSteps,
  randomPhone,
} from "./helpers";

const LOCALES = ["en", "ta", "hi"] as const;

/** localePrefix is "as-needed" with defaultLocale "en", so English is
 * UNPREFIXED and only ta/hi carry a segment (apps/web-milk/i18n/routing.ts). */
const prefix = (locale: (typeof LOCALES)[number]) => (locale === "en" ? "" : `/${locale}`);

/** Public routes only. A bare city slug (/coimbatore) is a deliberate 404 -
 * D28 chose not to ship a city landing page - so it is not swept. */
const PUBLIC_ROUTES = [
  "/",
  "/coimbatore/641001",
  "/c/milk",
  "/search",
  "/post-need",
  "/offline",
  "/directory/businesses/e2e-milk-vendor",
];

const TAMIL = /[஀-௿]/;
const DEVANAGARI = /[ऀ-ॿ]/;

/** A layout break is a page wider than its own viewport - which on a 360px
 * phone is exactly what longer Tamil and Hindi strings tend to cause. */
async function assertNoHorizontalOverflow(page: Page, where: string): Promise<void> {
  const { scroll, client } = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(scroll, `${where} overflows horizontally (${scroll}px inside ${client}px)`).toBeLessThanOrEqual(
    client + 1,
  );
}

/** An untranslated key leaks as its raw dotted path, e.g. "ui.pushAlerts.title". */
async function assertNoRawMessageKeys(page: Page, where: string): Promise<void> {
  const text = await page.locator("body").innerText();
  const leaked = text.match(/\b(?:ui|common)\.[a-zA-Z]+\.[a-zA-Z.]+/g);
  expect(leaked, `${where} renders untranslated message keys: ${leaked?.join(", ")}`).toBeNull();
}

test.describe("D29 vernacular pass", { tag: "@matrix" }, () => {
  for (const locale of LOCALES) {
    for (const route of PUBLIC_ROUTES) {
      test(`${locale} ${route} renders without breaking`, async ({ page }) => {
        await page.goto(`${MILK}${prefix(locale)}${route}`);
        // networkidle rather than a header wait: /offline deliberately renders
        // a bare shell, and this also lets the silent-SSO bounce finish before
        // anything is measured.
        await page.waitForLoadState("networkidle");
        await assertNoHorizontalOverflow(page, `${locale}${route}`);
        await assertNoRawMessageKeys(page, `${locale}${route}`);
      });
    }
  }

  test("ta renders the type filters in Tamil, not an English fallback", async ({ page }) => {
    await page.goto(`${MILK}/ta/coimbatore/641001`);
    await page.waitForLoadState("networkidle");
    const filters = await page.getByTestId("type-filter-row").innerText();
    expect(filters, "type filters fell back to English under /ta").toMatch(TAMIL);
  });

  test("hi actually applies the Hindi locale", async ({ page }) => {
    await page.goto(`${MILK}/hi/coimbatore/641001`);
    await page.waitForLoadState("networkidle");
    expect(await page.locator("body").innerText(), "the /hi page rendered no Devanagari").toMatch(
      DEVANAGARI,
    );
    // NOT asserted on the filter chips: MILK_TYPE_META (apps/web-milk/lib/milk.ts)
    // hardcodes `vern` as Tamil for every locale - "English + mother tongue",
    // UX law 1, for a Tamil-Nadu-first product. Spec D29.C asks for filters
    // "in Tamil", which holds; that a Hindi reader also sees Tamil sublabels is
    // a real gap but a product decision, so it is recorded in
    // docs/qa/d29-device-matrix.md rather than changed here.
  });

  test("the locale switcher keeps you on the same route", async ({ page }) => {
    await page.goto(`${MILK}/coimbatore/641001`);
    await page.waitForLoadState("networkidle");
    // The switcher is a nav of links (EN / TA / HI), not a <select>. `exact`
    // matters: the post-need CTA's accessible name also contains "த".
    await page.getByRole("link", { name: "த", exact: true }).click();
    await expect(page).toHaveURL(/\/ta\/coimbatore\/641001/, { timeout: 30_000 });
    // Let the switched page settle before the next hop: on WebKit a click that
    // lands while the new page is still hydrating is simply dropped.
    await page.waitForLoadState("networkidle");
    await page.getByRole("link", { name: "हिं", exact: true }).click();
    await expect(page).toHaveURL(/\/hi\/coimbatore\/641001/, { timeout: 30_000 });
  });
});

test.describe("D29 vernacular pass (signed in)", { tag: "@matrix" }, () => {
  test.skip(({ browserName }) => browserName === "webkit", WEBKIT_HTTP_COOKIE_SKIP);

  test("my-needs and notifications hold up in all three locales", async ({ page }) => {
    // Log in ONCE and revisit, rather than authenticating six times. /my-needs
    // renders a client island for guests instead of redirecting, so enter the
    // BFF dance explicitly rather than expecting a login form to appear.
    const phone = randomPhone();
    await page.goto(`${MILK}/api/auth/login?next=%2Fmy-needs`);
    await completeLoginUi(page, phone);
    await completeNewUserSteps(page);
    await expect(page).toHaveURL(/my-needs/, { timeout: 30_000 });

    for (const locale of LOCALES) {
      for (const route of ["/my-needs", "/notifications"]) {
        await page.goto(`${MILK}${prefix(locale)}${route}`);
        await page.waitForLoadState("networkidle");
        await assertNoHorizontalOverflow(page, `${locale}${route}`);
        await assertNoRawMessageKeys(page, `${locale}${route}`);
      }
    }
  });
});
