/**
 * A-U1 CP3 — agri.in home regression (build prompt §4).
 *
 * Every flag assertion is DOM SHAPE (node counts), never visibility: the
 * A11 lesson — a flag-off section must be ABSENT, not hidden. No
 * `waitUntil: "networkidle"` anywhere (coins pill / bell / hero carousel
 * poll forever).
 *
 * Flag flipping: `agri_today` is a public.feature_flags row consumed by the
 * API at the boundary (GET /market/today/{pincode} 404s while off). The
 * suite flips it with direct SQL through the dev postgres container — the
 * exact pattern push-verification.spec.ts established (execFileSync +
 * argv array, no shell) — and then POLLS the endpoint until the API's
 * in-process flag cache (FLAG_CACHE_TTL_SECONDS = 30, shared/flags.py)
 * has expired and the flip is live. The e2e host uvicorn and the docker
 * stack share the same postgres container, so one UPDATE serves both.
 * The suite restores the flag ON at the end (dev screenshots depend on it).
 */
import { execFileSync } from "node:child_process";

import { expect, request, test } from "@playwright/test";

import { AGRI, API, waitForHeaderSettled } from "./helpers";

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

/** Flip the flag and wait until the API actually serves the new state —
 * the 30s flag cache makes the SQL write alone insufficient. */
async function setAgriToday(enabled: boolean): Promise<void> {
  sql(
    `INSERT INTO public.feature_flags (key, enabled) VALUES ('agri_today', ${enabled})
     ON CONFLICT (key) DO UPDATE SET enabled = EXCLUDED.enabled`,
  );
  const ctx = await request.newContext();
  await expect
    .poll(async () => (await ctx.get(`${API}/market/today/641001`)).status(), {
      timeout: 45_000,
      intervals: [1_000],
    })
    .toBe(enabled ? 200 : 404);
  await ctx.dispose();
}

// Leave the flag ON when the suite is done — dev is currently demoing flag-on.
test.afterAll(async () => {
  await setAgriToday(true);
});

/** The flag-gated testids/anchors §2b/§3/§6b/§7/§8/§9 render. */
const FLAG_TESTIDS = ["severe-alert-strip", "today-strip", "mandi-ticker", "mandi-card"] as const;
const FLAG_ANCHORS = ["#mandi", "#weather", "#schemes"] as const;

test.describe("A-U1 guest console hygiene", () => {
  test("guest navigation logs zero console errors and zero 401s", async ({ page }) => {
    const consoleErrors: string[] = [];
    const unauthorized: string[] = [];
    page.on("console", (msg) => {
      // Same single, documented dev-only exclusion as milk-home.spec.ts:
      // React's hydration-mismatch warning fires under `next dev` because
      // AdUnit branches target/rel on `typeof window` (ad-slot.tsx,
      // pre-existing, logged in polish-u1.md §9.4). Production hydration
      // never compares attributes, so the acceptance run doesn't see it.
      // Everything else stays zero.
      if (msg.type() === "error" && !msg.text().startsWith("A tree hydrated but")) {
        consoleErrors.push(msg.text());
      }
    });
    page.on("response", (res) => {
      if (res.status() === 401) unauthorized.push(res.url());
    });
    for (const path of ["/", "/categories", "/tools", "/c/seeds"]) {
      await page.goto(`${AGRI}${path}`);
      await waitForHeaderSettled(page);
    }
    expect(unauthorized).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });

  test("FAQ JSON-LD is present on the home", async ({ page }) => {
    await page.goto(`${AGRI}/`);
    const jsonLd = page.locator('script[type="application/ld+json"]');
    await expect(jsonLd).toHaveCount(1);
    expect(await jsonLd.textContent()).toContain('"FAQPage"');
  });
});

test.describe("A-U1 agri_today OFF — sections absent from the DOM", () => {
  test.beforeAll(async () => {
    await setAgriToday(false);
  });

  test("flag-gated sections have node count 0; sarkari + tools persist", async ({ page }) => {
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
    for (const id of FLAG_TESTIDS) {
      await expect(page.getByTestId(id), `${id} must be ABSENT with the flag off`).toHaveCount(0);
    }
    for (const anchor of FLAG_ANCHORS) {
      await expect(page.locator(anchor), `${anchor} must be ABSENT with the flag off`).toHaveCount(
        0,
      );
    }
    // §9b sarkari and §10c tools are REAL, flag-independent surfaces.
    await expect(page.getByTestId("sarkari-link")).toHaveCount(6);
    await expect(page.locator('a[href^="/tools#"]')).toHaveCount(4);
  });
});

test.describe("A-U1 agri_today ON — payload-bound sections render", () => {
  test.beforeAll(async () => {
    await setAgriToday(true);
  });

  test("today strip, severe strip, ticker, 8 mandi cards, anchors present", async ({ page }) => {
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("today-strip")).toHaveCount(1);
    await expect(page.getByTestId("severe-alert-strip")).toHaveCount(1);
    await expect(page.getByTestId("mandi-ticker")).toHaveCount(1);
    await expect(page.getByTestId("mandi-card")).toHaveCount(8);
    for (const anchor of FLAG_ANCHORS) {
      await expect(page.locator(anchor)).toHaveCount(1);
    }
    await expect(page.getByTestId("scheme-card")).toHaveCount(3);
    await expect(page.getByTestId("deadlines-bar")).toHaveCount(1);
  });

  test("stamps render FROM the stub payload, never hardcoded", async ({ page }) => {
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
    // §7 row stamp: source + as-of from MandiBlock. (.first(): the text
    // engine can match an element AND its wrapping span.)
    await expect(
      page.locator("#mandi").getByText("Agmarknet (stub) · updated 6:00 AM").first(),
    ).toBeVisible();
    // §8 meta stamp: WeatherBlock.source verbatim.
    await expect(
      page.locator("#weather").getByText("Open-Meteo · IMD alerts (stub)").first(),
    ).toBeVisible();
    // §9 verification stamp: verified_against + verified_on from the payload.
    await expect(
      page
        .locator("#schemes")
        .getByText(/Verified against pmkisan\.gov\.in · 2026-08-12/)
        .first(),
    ).toBeVisible();
    // §9 deadlines: the PMFBY 72-hr intimation chip + helpline number.
    await expect(page.getByTestId("deadlines-bar").getByText("72 HRS").first()).toBeVisible();
    await expect(page.getByTestId("deadlines-bar").getByText(/14447/).first()).toBeVisible();
  });

  test("reduced motion: sparklines fully drawn, tiles opaque, marquee static", async ({
    browser,
  }) => {
    // A DEDICATED context with reducedMotion set explicitly, not the shared
    // fixture: the sweep's whole point is the prefers-reduced-motion media
    // state at Reveal's mount, and one run observed the pre-reveal held
    // state (stroke-dashoffset 120 on all 8 sparks) — i.e. the inherited
    // emulation was not in effect when the effect sampled matchMedia. Owning
    // the context pins the emulation to this page deterministically.
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("mandi-card")).toHaveCount(8);
    const sweep = await page.evaluate(() => {
      const polylines = Array.from(
        document.querySelectorAll<SVGPolylineElement>('[data-testid="mandi-card"] svg polyline'),
      );
      const offsets = polylines.map((pl) => getComputedStyle(pl).strokeDashoffset);
      const hiddenSparks = offsets.filter(
        (offset) => !(offset === "0px" || offset === "0" || offset === "none"),
      ).length;
      // §6 staggered pop-in wrappers (inline animation-delay) must land at
      // opacity 1 — never stuck at the pre-reveal opacity-0 state.
      const tiles = Array.from(
        document.querySelectorAll<HTMLElement>('[style*="animation-delay"]'),
      );
      const hiddenTiles = tiles.filter((el) => getComputedStyle(el).opacity !== "1").length;
      const lane = document.querySelector<HTMLElement>('[data-testid="mandi-ticker"] > div');
      return {
        polylineCount: polylines.length,
        offsets,
        hiddenSparks,
        tileCount: tiles.length,
        hiddenTiles,
        laneAnimation: lane ? getComputedStyle(lane).animationName : "missing",
      };
    });
    expect(sweep.polylineCount).toBe(8);
    expect(
      sweep.hiddenSparks,
      `sparklines must render fully drawn under reduced motion (offsets: ${sweep.offsets.join(", ")})`,
    ).toBe(0);
    expect(sweep.tileCount).toBeGreaterThanOrEqual(36);
    expect(sweep.hiddenTiles, "category tiles must land at opacity 1").toBe(0);
    expect(sweep.laneAnimation, "marquee lane must be static under reduced motion").toBe("none");
    await context.close();
  });

  test(".tap-target is never position:absolute (home, categories, tools)", async ({ page }) => {
    for (const path of ["/", "/categories", "/tools"]) {
      await page.goto(`${AGRI}${path}`);
      await waitForHeaderSettled(page);
      const offenders = await page.evaluate(() =>
        Array.from(document.querySelectorAll<HTMLElement>(".tap-target"))
          .filter((el) => getComputedStyle(el).position === "absolute")
          .map((el) => `<${el.tagName.toLowerCase()}> ${(el.textContent ?? "").trim().slice(0, 40)}`),
      );
      expect(offenders, `${path}: .tap-target must never be position:absolute`).toEqual([]);
    }
  });
});

test.describe("A-U1 locale contexts (one context per locale — NEXT_LOCALE trap)", () => {
  test.beforeAll(async () => {
    await setAgriToday(true);
  });

  // web-agri has NO locale URL segments: the request locale is the
  // NEXT_LOCALE cookie (i18n/request.ts). A cookie set mid-context leaks
  // into later navigations, so every locale gets a FRESH context.
  const CASES = [
    // Payload-bound TA (mandi title) + static TA on /categories.
    { locale: "ta", home: "சந்தை விலை", categories: "எல்லா பிரிவுகளும்" },
    // Payload-bound HI + static HI.
    { locale: "hi", home: "मंडी भाव", categories: "सभी श्रेणियां" },
  ] as const;

  for (const { locale, home, categories } of CASES) {
    test(`${locale}: home and /categories render translated strings`, async ({ browser }) => {
      const context = await browser.newContext();
      await context.addCookies([{ name: "NEXT_LOCALE", value: locale, url: AGRI }]);
      const page = await context.newPage();
      await page.goto(`${AGRI}/`);
      await waitForHeaderSettled(page);
      await expect(page.getByText(home).first()).toBeVisible();
      await page.goto(`${AGRI}/categories`);
      await expect(page.getByText(categories).first()).toBeVisible();
      await context.close();
    });
  }

  test("en context still renders the English home", async ({ browser }) => {
    const context = await browser.newContext(); // no cookie = en default
    const page = await context.newPage();
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
    await expect(page.getByText("Mandi prices").first()).toBeVisible();
    await context.close();
  });
});

test.describe("A-U1 production no-secret guest render", () => {
  // TODO(harness): the §2b milk lesson spec needs a PRODUCTION `next build`
  // + `next start` of web-agri with AUTH_SESSION_SECRET unset, asserting /
  // renders the guest home (Login pill, no 500). Playwright's webServer list
  // boots `next dev` with the repo env, so this cannot run inline — it needs
  // the same kind of separate harness as push-verification.spec.ts (owner-
  // run) or a dedicated CI job that builds without the secret (the
  // lhci-affected.mjs web-admin note documents the failure mode). Skipped
  // until that harness exists; recorded in the CP3 report.
  test.skip(true, "needs a prod build/start harness without AUTH_SESSION_SECRET (see TODO above)");

  test("no-secret production boot renders the guest home", async ({ page }) => {
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
  });
});
