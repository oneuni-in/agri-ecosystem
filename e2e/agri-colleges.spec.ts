import { expect, request, test } from "@playwright/test";

import { AGRI, API } from "./helpers";

/**
 * Every navigation goes through here.
 *
 * A bare second `page.goto` in one test aborts with net::ERR_ABORTED against
 * the dev server: the first page's RSC stream is still in flight while the
 * next route compiles on demand, and Chromium cancels the navigation. The
 * routes are fine -- each of these URLs answers 200 to curl. Settling the
 * previous load first is what makes a multi-navigation test honest rather
 * than flaky.
 */
async function visit(page: import("@playwright/test").Page, path: string) {
  // "load", not "domcontentloaded": a streamed RSC page fires DCL while the
  // body is still arriving, and CI's trace snapshot proved it -- the failure
  // screenshot showed every article present milliseconds after a count()
  // returned 0. "load" waits for the stream to close.
  await page.goto(`${AGRI}${path}`, { waitUntil: "load" });
  await page.waitForLoadState("networkidle").catch(() => {});
}

/**
 * Phase 2 — the agri-colleges surfaces.
 *
 * Tagged `@matrix` deliberately. `e2e:matrix` selects on that tag and
 * `e2e:auth` runs a named list, so an UNTAGGED spec outside that list runs in
 * neither CI job. `e2e/agri-categories.spec.ts` is in exactly that position
 * today, which is how its `toBe(36)` assertion went two days without anyone
 * noticing migration 0042 had made it false.
 *
 * Slugs are looked up from the API rather than hardcoded. The corpus is
 * reseeded from CSV on every data PR, so a hardcoded slug rots on the next
 * one and fails as if the page were broken.
 */

interface Card {
  slug: string;
  name: string;
  trust: string;
  can_show_admission_data: boolean;
}

async function firstInstitution(trust: "verified" | "listed"): Promise<Card | undefined> {
  const ctx = await request.newContext();
  const res = await ctx.get(`${API}/education/institutions?trust=${trust}&limit=1`);
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as { items: Card[] };
  await ctx.dispose();
  return body.items[0];
}

test.describe("Phase 2 agri-colleges", { tag: "@matrix" }, () => {
  test("/colleges lists colleges and filters server-side", async ({ page }) => {
    await visit(page, "/colleges");
    await expect(page.locator("h1")).toContainText(/colleges/i);
    // toBeVisible auto-retries; a bare count() reads instantly and races the
    // stream (the CI failure mode this spec shipped with).
    await expect(page.locator("article").first()).toBeVisible();
    const all = await page.locator("article").count();
    expect(all).toBeGreaterThan(0);

    // Government-only is a plain link, so this also proves the filter works
    // with no JS involved in producing the result.
    await visit(page, "/colleges?gov=true");
    await expect(page.locator("article").first()).toBeVisible();
    const gov = await page.locator("article").count();
    expect(gov).toBeGreaterThan(0);
    expect(gov).toBeLessThanOrEqual(all);
  });

  test("a state page renders, and an unknown state 404s", async ({ page, request: req }) => {
    const res = await req.get(`${API}/education/states`);
    const states = (await res.json()) as { slug: string; name: string }[];
    expect(states.length).toBeGreaterThan(0);

    const first = states[0]!;
    await visit(page, `/colleges/state/${first.slug}`);
    await expect(page.locator("h1")).toContainText(first.name);
    await expect(page.locator("article").first()).toBeVisible();

    const missing = await req.get(`${AGRI}/colleges/state/atlantis`);
    expect(missing.status()).toBe(404);
  });

  test("a listed college shows no fee and no seat count", async ({ page }) => {
    const row = await firstInstitution("listed");
    test.skip(!row, "no listed rows in the seeded corpus");

    await visit(page, `/colleges/${row!.slug}`);
    // The honest notice is present...
    await expect(page.getByText(/not yet checked/i)).toBeVisible();
    // ...and no rupee figure appears anywhere on the page.
    await expect(page.locator("body")).not.toContainText(/₹\s*\d/);
    // The page is noindex, so it can never be advertised.
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
      "content",
      /noindex/,
    );
  });

  test("a verified college carries its JSON-LD and is indexable", async ({ page }) => {
    const row = await firstInstitution("verified");
    test.skip(!row, "no verified rows in the seeded corpus");

    await visit(page, `/colleges/${row!.slug}`);
    const ldScripts = page.locator('script[type="application/ld+json"]');
    // toHaveCount auto-retries where allTextContents reads instantly -- and a
    // late navigation (silent-SSO bounce, dev-server replace) destroyed the
    // context mid-read in CI. Wait for both blocks, THEN read.
    await expect(ldScripts).toHaveCount(2);
    const ld = await ldScripts.allTextContents();
    expect(ld.join(" ")).toContain("CollegeOrUniversity");
    expect(ld.join(" ")).toContain("BreadcrumbList");
    // Indexable: no robots meta at all, or one that does not say noindex.
    const robots = await page.locator('meta[name="robots"]').count();
    if (robots > 0) {
      await expect(page.locator('meta[name="robots"]')).not.toHaveAttribute(
        "content",
        /noindex/,
      );
    }
  });

  test("guides render their steps in order with a verified-on stamp", async ({
    page,
    request: req,
  }) => {
    const res = await req.get(`${API}/education/guides?kind=counselling`);
    const guides = (await res.json()) as { slug: string }[];
    test.skip(guides.length === 0, "no counselling guides seeded");

    await visit(page, "/counselling");
    await expect(page.locator("article").first()).toBeVisible();

    await visit(page, `/guides/${guides[0]!.slug}`);
    // An ordered list, because counselling rounds happen in sequence and a
    // shuffled list is actively misleading.
    await expect(page.locator("ol > li").first()).toBeVisible();
    await expect(page.getByText(/checked/i).first()).toBeVisible();
  });

  test("the registry tile is live and links to /colleges", async ({ page }) => {
    await visit(page, "/categories");
    await expect(page.locator('a[href="/c/agri-colleges"]')).toHaveCount(1);

    // The tile is live, not Soon: /c/agri-colleges sends readers on to the
    // real surface rather than to a landing page.
    await visit(page, "/c/agri-colleges");
    await expect(page.locator('a[href="/colleges"]').first()).toBeVisible();
  });

  test("the sitemap advertises verified colleges and no listed ones", async ({
    request: req,
  }) => {
    const listed = await firstInstitution("listed");
    const verified = await firstInstitution("verified");
    const xml = await (await req.get(`${AGRI}/sitemap.xml`)).text();

    if (verified) expect(xml).toContain(`/colleges/${verified.slug}<`);
    // A listed page is noindex; advertising a self-noindexed page to Google
    // is the failure this assertion exists to prevent.
    if (listed) expect(xml).not.toContain(`/colleges/${listed.slug}<`);
  });
});
