import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { API, MILK, waitForHeaderSettled } from "./helpers";

const SCREENS = [
  { name: "home", path: "/" },
  { name: "pincode landing", path: "/coimbatore/641001" },
  { name: "category", path: "/c/dairy-farm" },
  { name: "search", path: "/search" },
  { name: "post-need", path: "/post-need" },
];

test.describe("D29 accessibility sweep", { tag: "@matrix" }, () => {
  for (const screen of SCREENS) {
    test(`${screen.name} has no serious or critical violations`, async ({ page }) => {
      await page.goto(`${MILK}${screen.path}`);
      // networkidle, plus a tolerant header wait: the silent-SSO bounce can
      // fire a navigation AFTER the network goes quiet and destroy axe's
      // execution context mid-analysis. Tolerant because /c/* renders no
      // logged-out Login button to wait for.
      await page.waitForLoadState("networkidle");
      await waitForHeaderSettled(page).catch(() => {});

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        // Next's dev overlay is not product UI.
        .exclude("nextjs-portal")
        // Known, owner-accepted exception, scoped to ONE selector rather than
        // disabling color-contrast globally: the translucent header pills
        // (`bg-glass`, white text over the brand gradient) are a signature
        // treatment from docs/design-system.md, and clearing 4.5:1 there means
        // a visual redesign rather than a bug fix. Deferred deliberately and
        // logged with its ratio in docs/qa/d29-device-matrix.md (D29).
        // color-contrast stays live on everything else on the page.
        .exclude(".bg-glass")
        // The pre-existing D02 call/rating conflict, likewise scoped to the
        // exact selector. The Call CTA is white on --call #1E9E4A = 3.47:1,
        // under the 4.5:1 floor. That green is fixed by docs/design-system.md
        // (the mockup is the visual source of truth per CLAUDE.md) and the
        // conflict was accepted when D02 set the tokens - "call > chat > form"
        // wants that button unmistakable. Recorded with its ratio in the
        // matrix; changing it is a design decision, not a QA fix.
        .exclude(".bg-call")
        .analyze();

      const blocking = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      );
      const detail = blocking
        .map((v) => `${v.id} (${v.impact}) x${v.nodes.length}: ${v.help}\n    ${v.nodes[0]?.html?.slice(0, 160)}`)
        .join("\n");
      expect(blocking, `${screen.name}:\n${detail}`).toEqual([]);
    });
  }

  test("the contact CTA names itself for a screen reader", async ({ page, request }) => {
    const home = await request.get(`${API}/catalog/milk/home/641001`);
    const { vendors } = (await home.json()) as { vendors: { slug: string }[] };
    const fixture = vendors.find((v) => v.slug === "e2e-milk-vendor");
    await page.goto(`${MILK}/directory/businesses/${fixture!.slug}`);
    await waitForHeaderSettled(page);
    // Guest state: the gate must still say what it does, not just show an icon.
    await expect(page.getByRole("link", { name: /login to view contact/i })).toBeVisible();
    // And the enquiry form's controls must be labelled.
    await expect(page.getByLabel(/message/i)).toBeVisible();
  });

  test("the milk type filters expose an accessible group and current state", async ({ page }) => {
    await page.goto(`${MILK}/coimbatore/641001`);
    await waitForHeaderSettled(page);
    const group = page.getByRole("group", { name: /milk type/i });
    await expect(group).toBeVisible();
    // The active filter must be announced, not merely coloured.
    await expect(group.locator("[aria-current='true']")).toHaveCount(1);
  });

  test("keyboard focus is visible on the first focusable control", async ({ page }) => {
    await page.goto(`${MILK}/coimbatore/641001`);
    await waitForHeaderSettled(page);
    await page.keyboard.press("Tab");
    const ring = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      const s = getComputedStyle(el);
      return { width: s.outlineWidth, style: s.outlineStyle, tag: el.tagName };
    });
    expect(ring, "nothing took focus on the first Tab").not.toBeNull();
    expect(
      ring!.style !== "none" && parseFloat(ring!.width) > 0,
      `focused <${ring!.tag}> has no visible focus ring (outline: ${ring!.style} ${ring!.width})`,
    ).toBeTruthy();
  });
});
