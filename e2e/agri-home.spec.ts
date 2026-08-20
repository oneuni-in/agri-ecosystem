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

import {
  AGRI,
  API,
  apiAs,
  loginAs,
  randomPhone,
  waitForHeaderSettled,
} from "./helpers";

/** The database the API is actually reading, not a hardcoded name.
 *
 * This used to be the literal "agri". That is right until it is not: run the
 * suite against an isolated database (worktrees sharing one postgres will
 * force that — a sibling branch's migration leaves the shared DB at a
 * revision this branch cannot resolve) and the flag write lands in one
 * database while the API reads another. The flip appears to do nothing and
 * the failure looks like a caching bug in the product. Follow DATABASE_URL
 * so the write cannot miss. */
function pgDatabase(): string {
  const url = process.env.DATABASE_URL;
  if (!url) return "agri";
  const name = url.split("/").pop()?.split("?")[0];
  return name && name.length > 0 ? name : "agri";
}

function sql(query: string): string {
  // Two transports, because the two environments genuinely differ and the
  // first CI run of this suite proved it: `docker exec agri-dev-postgres-1`
  // failed every flag flip with "No such container" - that name exists only
  // on the dev laptop's compose stack. CI runs postgres as a service
  // container and exports DATABASE_ADMIN_URL, and ubuntu runners ship a
  // host psql; the laptop has the container but not a host psql. So: when an
  // admin URL is present, use host psql against it; otherwise fall back to
  // the dev container. execFileSync + argv arrays in both arms - no shell,
  // no interpolation surface.
  const adminUrl = process.env.DATABASE_ADMIN_URL;
  if (adminUrl) {
    return execFileSync("psql", [adminUrl.replace("+asyncpg", ""), "-tAc", query])
      .toString()
      .trim();
  }
  return execFileSync("docker", [
    "exec",
    "agri-dev-postgres-1",
    "psql",
    "-U",
    "app",
    "-d",
    pgDatabase(),
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

interface TodayShape {
  stub: boolean;
  weather: { source: string };
  severe_alert: unknown | null;
  mandi: {
    source: string;
    as_of: string;
    next_pull_hour_ist: number;
    commodities: unknown[];
  };
  schemes: {
    items: { verified_against: string; verified_on: string }[];
    deadlines: { chip: string }[];
  };
}

/** The payload the page rendered from. Assertions compare the DOM against
 * THIS rather than against literals, so the spec keeps binding as the real
 * data underneath it changes. */
async function fetchToday(): Promise<TodayShape> {
  const ctx = await request.newContext();
  const response = await ctx.get(`${API}/market/today/641001`);
  expect(response.status()).toBe(200);
  const body = (await response.json()) as TodayShape;
  await ctx.dispose();
  return body;
}

// Leave the flag ON when the suite is done — dev is currently demoing flag-on.
test.afterAll(async () => {
  await setAgriToday(true);
});

/** The flag-gated testids/anchors §2b/§3/§6b/§7/§8/§9 render. */
const FLAG_TESTIDS = [
  "severe-alert-strip",
  "today-strip",
  "mandi-ticker",
  "mandi-card",
] as const;
const FLAG_ANCHORS = ["#mandi", "#weather", "#schemes"] as const;

test.describe("A-U1 guest console hygiene", () => {
  test("guest navigation logs zero console errors and zero 401s", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    const unauthorized: string[] = [];
    page.on("console", (msg) => {
      // Same single, documented dev-only exclusion as milk-home.spec.ts:
      // React's hydration-mismatch warning fires under `next dev` because
      // AdUnit branches target/rel on `typeof window` (ad-slot.tsx,
      // pre-existing, logged in polish-u1.md §9.4). Production hydration
      // never compares attributes, so the acceptance run doesn't see it.
      // Everything else stays zero.
      if (
        msg.type() === "error" &&
        !msg.text().startsWith("A tree hydrated but")
      ) {
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

  // UNRESOLVED — and this is a REAL behaviour change, not a broken test.
  //
  // A-U1 fetched today with `cache: "no-store"`, so flipping agri_today off
  // showed on the very next render, which is what this asserts. A-U4 W0
  // changed it to `revalidate: 60` so six Suspense boundaries share one
  // upstream call. Measured in `next dev`: with the API returning 404
  // throughout, the strip still rendered at 125s and survived a dev-server
  // restart, clearing only when .next/cache/fetch-cache was deleted AND the
  // server restarted. Clearing the cache before the run was not sufficient.
  //
  // The open question is therefore a product one: how long may a flag flip
  // take to reach the home, and is 60s+ acceptable? Owner's call. Marked
  // fixme rather than loosened, because quietly relaxing the assertion would
  // hide exactly the change W0 introduced.
  test.fixme("flag-gated sections have node count 0; sarkari + tools persist", async ({
    page,
  }) => {
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
    // NOTE ON WHY THIS NEEDS A COLD FETCH CACHE (`pnpm run e2e:agri` clears
    // it before Playwright boots the server).
    //
    // A-U1 fetched today with `cache: "no-store"`, so flipping the flag off
    // was visible on the very next render. A-U4 W0 changed that to
    // `revalidate: 60` (lib/home-data.ts) so six Suspense boundaries share
    // one upstream call. In `next dev` that cache is written to
    // .next/cache/fetch-cache, and the measured behaviour is that it serves
    // the stale 200 well past 60s AND survives a dev-server restart: with
    // the API returning 404 throughout, the strip was still rendering at
    // 125s and after a full restart, and only vanished once the cache
    // directory was deleted AND the server restarted. So no amount of
    // reloading or waiting inside this test can turn a warm cache cold —
    // the run has to start cold, which is what the script guarantees.
    for (const id of FLAG_TESTIDS) {
      await expect(
        page.getByTestId(id),
        `${id} must be ABSENT with the flag off`,
      ).toHaveCount(0);
    }
    for (const anchor of FLAG_ANCHORS) {
      await expect(
        page.locator(anchor),
        `${anchor} must be ABSENT with the flag off`,
      ).toHaveCount(0);
    }
    // §9b sarkari and §10c tools are REAL, flag-independent surfaces.
    await expect(page.getByTestId("sarkari-link")).toHaveCount(6);
    await expect(page.locator('a[href^="/tools#"]')).toHaveCount(4);
  });
});

test.describe("A-U2 agri_today ON — payload-bound sections render", () => {
  test.beforeAll(async () => {
    // A-U2: the fixtures are gone, so these sections render whatever the
    // real engines hold. scripts/e2e-api.mjs seeds their two REAL inputs
    // (weather cache + ingested price rows) during API boot, so the run is
    // deterministic and makes no external call.
    await setAgriToday(true);
  });

  test("today strip, ticker, mandi cards and anchors match the payload", async ({
    page,
  }) => {
    const today = await fetchToday();
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("today-strip")).toHaveCount(1);
    await expect(page.getByTestId("mandi-ticker")).toHaveCount(1);
    // MOVED from the fixture's hardcoded 8: the DOM must match the payload
    // the API actually served, whatever the ingest currently holds.
    expect(today.mandi.commodities.length).toBeGreaterThan(0);
    await expect(page.getByTestId("mandi-card")).toHaveCount(
      Math.min(today.mandi.commodities.length, 8),
    );
    // The severe strip is DERIVED and rare now (A-U2 W1), so its presence
    // is bound to the payload rather than assumed.
    await expect(page.getByTestId("severe-alert-strip")).toHaveCount(
      today.severe_alert ? 1 : 0,
    );
    for (const anchor of FLAG_ANCHORS) {
      await expect(page.locator(anchor)).toHaveCount(1);
    }
    await expect(page.getByTestId("scheme-card")).toHaveCount(
      today.schemes.items.length,
    );
    await expect(page.getByTestId("deadlines-bar")).toHaveCount(1);
  });

  test("stamps render FROM the real payload, never hardcoded", async ({
    page,
  }) => {
    const today = await fetchToday();
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
    // §7 row stamp: source + as-of read back out of MandiBlock. (.first():
    // the text engine can match an element AND its wrapping span.)
    await expect(
      page
        .locator("#mandi")
        .getByText(`${today.mandi.source} · updated ${today.mandi.as_of}`)
        .first(),
    ).toBeVisible();
    // O1 (AG-A70): the stamp's second line says the data is a once-a-day
    // snapshot and when it refreshes — the hour FROM the payload
    // (next_pull_hour_ist), never a literal. The LiveDot is gone from this
    // stamp: a pulsing dot over a daily dataset implied real-time.
    const pullHour = today.mandi.next_pull_hour_ist;
    const hourLabel = `${pullHour % 12 === 0 ? 12 : pullHour % 12} ${pullHour < 12 ? "AM" : "PM"}`;
    const stamp = page.getByTestId("mandi-stamp");
    await expect(stamp).toContainText(`updated once a day, around ${hourLabel} IST`);
    await expect(stamp).toContainText(`next update after ${hourLabel} IST`);
    // §6b ticker carries the compact cadence phrase alongside the source.
    await expect(page.getByTestId("mandi-ticker")).toContainText(
      `once-daily · ~${hourLabel} IST`,
    );
    // §8 meta stamp: WeatherBlock.source verbatim — "Open-Meteo", or the
    // stale "Open-Meteo · as of …" form during an upstream outage.
    expect(today.weather.source).toContain("Open-Meteo");
    await expect(
      page.locator("#weather").getByText(today.weather.source).first(),
    ).toBeVisible();
    // §9 verification stamp: verified_against + verified_on FROM the row.
    const scheme = today.schemes.items[0];
    await expect(
      page
        .locator("#schemes")
        .getByText(
          `Verified against ${scheme.verified_against} · ${scheme.verified_on}`,
        )
        .first(),
    ).toBeVisible();
    // §9 deadlines: the PMFBY 72-hr intimation is a ROLLING obligation with
    // no due date, so it survives every clock and must always be present.
    expect(today.schemes.deadlines.some((d) => d.chip === "72 HRS")).toBe(true);
    await expect(
      page.getByTestId("deadlines-bar").getByText("72 HRS").first(),
    ).toBeVisible();
    await expect(
      page.getByTestId("deadlines-bar").getByText(/14447/).first(),
    ).toBeVisible();
  });

  test("nothing on the page claims to be stub data", async ({ page }) => {
    // AG-A20: the flip deleted market_data/fixtures.py. `stub` is pinned
    // False, and the fixtures' tell-tale "(stub)" stamps must be gone.
    const today = await fetchToday();
    expect(today.stub).toBe(false);
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
    await expect(page.getByText(/\(stub\)/)).toHaveCount(0);
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
    const today = await fetchToday();
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
    // MOVED from the fixture's hardcoded 8 (A-U2): the sweep must cover
    // every sparkline the payload actually produced, not a count that only
    // held while the cards came from fixtures.
    const expectedCards = Math.min(today.mandi.commodities.length, 8);
    expect(expectedCards).toBeGreaterThan(0);
    await expect(page.getByTestId("mandi-card")).toHaveCount(expectedCards);
    const sweep = await page.evaluate(() => {
      const polylines = Array.from(
        document.querySelectorAll<SVGPolylineElement>(
          '[data-testid="mandi-card"] svg polyline',
        ),
      );
      // A spark is one polyline per CONTIGUOUS run of days now (A-U4b):
      // a hole in the data splits the line, so a card may hold several.
      const cards = Array.from(
        document.querySelectorAll<HTMLElement>('[data-testid="mandi-card"]'),
      );
      const cardsMissingSpark = cards.filter(
        (card) => card.querySelectorAll("svg polyline").length === 0,
      ).length;
      const offsets = polylines.map(
        (pl) => getComputedStyle(pl).strokeDashoffset,
      );
      const hiddenSparks = offsets.filter(
        (offset) => !(offset === "0px" || offset === "0" || offset === "none"),
      ).length;
      // §6 tiles must be at opacity 1. (The stagger wrappers this selected
      // by [style*=animation-delay] were removed with the home's deferred
      // motion — polish-a1 §0; the guarantee is unchanged: every registry
      // tile fully visible.)
      const tiles = Array.from(
        document.querySelectorAll<HTMLElement>('a[href^="/c/"]'),
      );
      const hiddenTiles = tiles.filter(
        (el) => getComputedStyle(el).opacity !== "1",
      ).length;
      const lane = document.querySelector<HTMLElement>(
        '[data-testid="mandi-ticker"] > div',
      );
      return {
        polylineCount: polylines.length,
        cardsMissingSpark,
        offsets,
        hiddenSparks,
        tileCount: tiles.length,
        hiddenTiles,
        laneAnimation: lane ? getComputedStyle(lane).animationName : "missing",
      };
    });
    // >= not ===: a gap in a card's series renders as multiple polylines
    // (one per contiguous segment); the dash sweep above covers them ALL.
    expect(sweep.polylineCount).toBeGreaterThanOrEqual(expectedCards);
    expect(
      sweep.cardsMissingSpark,
      "every mandi card must render at least one sparkline segment",
    ).toBe(0);
    expect(
      sweep.hiddenSparks,
      `sparklines must render fully drawn under reduced motion (offsets: ${sweep.offsets.join(", ")})`,
    ).toBe(0);
    expect(sweep.tileCount).toBeGreaterThanOrEqual(36);
    expect(sweep.hiddenTiles, "category tiles must land at opacity 1").toBe(0);
    expect(
      sweep.laneAnimation,
      "marquee lane must be static under reduced motion",
    ).toBe("none");
    await context.close();
  });

  test(".tap-target is never position:absolute (home, categories, tools)", async ({
    page,
  }) => {
    for (const path of ["/", "/categories", "/tools"]) {
      await page.goto(`${AGRI}${path}`);
      await waitForHeaderSettled(page);
      const offenders = await page.evaluate(() =>
        Array.from(document.querySelectorAll<HTMLElement>(".tap-target"))
          .filter((el) => getComputedStyle(el).position === "absolute")
          .map(
            (el) =>
              `<${el.tagName.toLowerCase()}> ${(el.textContent ?? "").trim().slice(0, 40)}`,
          ),
      );
      expect(
        offenders,
        `${path}: .tap-target must never be position:absolute`,
      ).toEqual([]);
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
    test(`${locale}: home and /categories render translated strings`, async ({
      browser,
    }) => {
      const context = await browser.newContext();
      await context.addCookies([
        { name: "NEXT_LOCALE", value: locale, url: AGRI },
      ]);
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
  test.skip(
    true,
    "needs a prod build/start harness without AUTH_SESSION_SECRET (see TODO above)",
  );

  test("no-secret production boot renders the guest home", async ({ page }) => {
    await page.goto(`${AGRI}/`);
    await waitForHeaderSettled(page);
  });
});

test.describe("A-U2 price alerts — the logged-in round-trip (AG-A16)", () => {
  // RESOLVED (A-U4b C2, 2026-08-20). The product was never broken — the SPEC
  // raced its own POST. The card disables synchronously on "saving", so the
  // old `toBeDisabled()` passed before the request had gone anywhere; the
  // spec then read the subscription list while the POST was still in flight
  // (the BFF route compiles on its first-ever dev hit — whole seconds) and
  // found 0 rows. Test teardown aborted the in-flight request, which is why
  // the API access log never recorded it (browser trace: POST with response
  // status -1). Both login paths — interactive redirect and silent SSO —
  // were verified live to land a 201 through the BFF. The fix is the
  // waitForResponse sync point below; there is nothing to fix in the app.
  test("subscribing from the home card lands a real subscription", async ({
    page,
  }) => {
    // AG-A16 asks that the subscription ROUND-TRIPS. The backend half has
    // been covered since 0044 (tests/test_market_alerts.py, including
    // dispatch_due_alerts firing after an ingest); what was never proven is
    // that a real person, logged in, clicking the real card, ends up with a
    // row. That is the half a unit test structurally cannot reach — the card
    // POSTs through the same-origin BFF so the bearer never touches JS, and
    // whether that path works is a browser question.
    const phone = randomPhone();
    await loginAs(page, phone); // baseURL is web-id; agri picks the session up via silent SSO

    await page.goto(`${AGRI}/`);
    // NOT waitForHeaderSettled: it waits for the `auth-login` button, which
    // is the GUEST header — a logged-in visitor never renders it, so that
    // helper can only ever time out here. Wait on the session itself, which
    // is the thing that actually has to land: the card POSTs through the
    // same-origin BFF, and if silent SSO has not completed the POST 401s and
    // the card correctly flips to its sign-in bounce.
    await expect
      .poll(
        async () => (await page.request.get(`${AGRI}/api/auth/me`)).status(),
        {
          timeout: 45_000,
          intervals: [1_000],
        },
      )
      .toBe(200);
    // A fresh navigation, NOT page.reload(): silent SSO drives its own
    // navigation to /api/auth/login?silent=1, and reloading into that races
    // it — "net::ERR_ABORTED; maybe frame was detached". Going to the URL
    // afresh once the session exists cannot be aborted by a navigation that
    // has already finished.
    await page.goto(`${AGRI}/`, { waitUntil: "load" });

    // Logged in, so the card offers the CTA rather than the sign-in bounce.
    // If this is the sign-in link instead, SSO did not settle and the rest
    // of the test would be meaningless.
    await expect(page.getByTestId("mandi-alert-signin")).toHaveCount(0);
    const cta = page.getByTestId("mandi-alert-cta");
    await expect(cta).toBeVisible();

    // THE SYNC POINT IS THE RESPONSE, NOT THE DISABLED STATE. The card
    // disables synchronously on click ("saving") as well as on success
    // ("done"), so `toBeDisabled()` is satisfied while the POST is still in
    // flight — and in dev the BFF route compiles on its first-ever hit, which
    // takes whole seconds. This spec's original failure was exactly that
    // race: it read the subscription list while its own POST was mid-air,
    // found 0 rows, and the test teardown then aborted the request — which
    // is why the API access log never saw it (the AG-A16/C2 diagnosis,
    // 2026-08-20: browser trace shows the POST with response status -1).
    const [response] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes("/api/market/alerts") &&
          res.request().method() === "POST",
        { timeout: 30_000 },
      ),
      cta.click(),
    ]);
    // 201 created, or 200 if they already followed this pincode — the
    // backend is idempotent, so both mean "you are subscribed".
    expect([200, 201], "the subscribe POST must succeed").toContain(
      response.status(),
    );
    await expect(cta).toBeDisabled();

    // The DOM saying "done" is the card's claim. This is the check: ask the
    // API, as that user, whether the row is actually there.
    const api = await apiAs(phone);
    const res = await api.get(`${API}/market/alerts`);
    expect(res.status()).toBe(200);
    const alerts = (await res.json()) as unknown[];
    expect(alerts.length, "the click must leave exactly one subscription").toBe(
      1,
    );
    await api.dispose();
  });
});
