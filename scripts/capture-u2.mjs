// U2 Group A — console captures: the vendor dashboard at the four NN
// viewports, the consumer (nav-less) onboarding state, and the /demo
// kitchen-sink's U2 console section.
//
// Auth: the docker API does not run OTP_TEST_PEEK (that is scripts/
// e2e-api.mjs's rig), so the OTP is read from the container's mock-sms log
// line instead — the documented dev recipe. Each login costs one OTP from
// the 5/day per-phone budget; the script logs in ONCE per session type and
// reuses the context across viewports.
import { spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const OUT = process.env.OUT_DIR ?? "docs/design-reference/u2";
const AGRI = process.env.AGRI_URL ?? "http://localhost:3002";
const WIDTHS = [360, 768, 1024, 1440];
/** seed_e2e_milk.py: owns "E2E Milk Vendor" — the vendor session. */
const VENDOR_PHONE = process.env.VENDOR_PHONE ?? "9000000023";

mkdirSync(OUT, { recursive: true });

async function otpFromDockerLogs(phone) {
  // --tail with a SMALL window, not --since and not a big tail: the WSL VM
  // clock drifts after host sleep (a drifted daemon "now" makes --since
  // filter out everything), and large --tail values were observed to drop
  // recent stdout lines entirely on Docker Desktop for Windows. Poll a
  // 200-line window until the line lands (the mock-sms print can lag the
  // "sent" response by a moment).
  for (let attempt = 0; attempt < 15; attempt += 1) {
    const result = spawnSync("docker", ["logs", "agri-dev-api-1", "--tail", "200"], {
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    });
    const haystack = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
    const matches = [
      ...haystack.matchAll(
        new RegExp(`\\[mock-sms\\] to=\\+91${phone} purpose=login code=(\\d{6})`, "g"),
      ),
    ];
    if (matches.length > 0) return matches[matches.length - 1][1];
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`no mock-sms OTP in docker logs for ${phone}`);
}

/** Drive the BFF authorize dance from a console URL to a settled session. */
async function login(page, phone) {
  await page.goto(`${AGRI}/business`, { waitUntil: "load" });
  const input = page.getByLabel(/mobile number/i);
  await input.waitFor({ timeout: 45_000 });
  const send = page.getByRole("button", { name: /send otp/i });
  // Hydration-resilient fill (the e2e helpers' trick, minus expect()).
  for (let attempt = 0; attempt < 15; attempt += 1) {
    await input.fill("");
    await input.fill(phone);
    if (await send.isEnabled()) break;
    await page.waitForTimeout(1000);
  }
  await send.click();
  await page.getByText(/6-digit code/i).waitFor({ timeout: 20_000 });
  const code = await otpFromDockerLogs(phone);
  await page.getByRole("textbox", { name: /1\/6/ }).click();
  await page.keyboard.type(code, { delay: 40 });
  // New users walk the handle-skip + language steps; existing users resume
  // the authorize straight away.
  try {
    await page.getByRole("button", { name: /skip for now/i }).click({ timeout: 8_000 });
    await page.getByRole("button", { name: /english/i }).click({ timeout: 8_000 });
  } catch {
    /* existing user */
  }
  await page.waitForURL(new RegExp(`^${AGRI}/business`), { timeout: 90_000 });
}

async function shot(page, url, path, width, { full = false, element = null, ready = null } = {}) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(url, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  // `ready` is a role+name to wait for BEFORE capturing — the console pages
  // hydrate a client island that fetches businesses/products, so a bare
  // timeout captures Skeletons. networkidle never settles here (the header's
  // coins/bell islands poll — U1 §4 trap), so we wait on a real element.
  if (ready) await page.getByRole(ready.role, { name: ready.name }).first().waitFor({ timeout: 30_000 });
  await page.addStyleTag({ content: "*{animation-play-state:paused!important}" });
  await page.waitForTimeout(ready ? 1200 : 600);
  if (element) {
    const target = page.locator("section").filter({ hasText: element }).first();
    // animations:"disabled" — Playwright's own stabilizer; the demo page's
    // marquee keeps the element "unstable" under a bare screenshot() wait.
    await target.screenshot({ path, animations: "disabled", timeout: 30_000 });
  } else {
    await page.screenshot({ path, fullPage: full });
  }
  console.log(path);
}

const browser = await chromium.launch();

// 1) Vendor session: dashboard at the four viewports + full-page record.
// (DEMO_ONLY=1 skips both login sections — each login costs OTP budget.)
// The vendor logs in ONCE; the session's storage state is reused for the
// dashboard AND the Group B listings/products locales. Each login costs one
// of the phone's 5/day OTPs, so a second vendor login per run exhausts it.
let vendorState = null;
if (!process.env.DEMO_ONLY) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, VENDOR_PHONE);
  vendorState = await context.storageState();
  for (const w of WIDTHS) {
    await shot(page, `${AGRI}/business`, `${OUT}/console-dashboard-${w}.png`, w);
  }
  await shot(page, `${AGRI}/business`, `${OUT}/console-dashboard-full-1440.png`, 1440, {
    full: true,
  });
  await context.close();
}

// 2) Consumer session (fresh phone, owns nothing): onboarding, no nav.
if (!process.env.DEMO_ONLY) {
  const phone = `9${Math.floor(100_000_000 + Math.random() * 899_999_999)}`;
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, phone);
  await shot(page, `${AGRI}/business`, `${OUT}/console-onboarding-360.png`, 360);
  await shot(page, `${AGRI}/business`, `${OUT}/console-onboarding-1440.png`, 1440);
  await context.close();
}

// 2b) Group B: vendor listings + products pages, EN + TA + HI (NON-NEG 4).
// Each locale gets its own browser context (the next-intl NEXT_LOCALE-cookie
// trap from U1 §4), reusing the ONE vendor session captured above.
if (!process.env.DEMO_ONLY && vendorState) {
  const state = vendorState;
  for (const loc of ["en", "ta", "hi"]) {
    const locContext = await browser.newContext({
      storageState: state,
      // the switcher writes this cookie; seed it so the page renders in `loc`
      // without a click round-trip
    });
    await locContext.addCookies([
      { name: "NEXT_LOCALE", value: loc, url: AGRI },
    ]);
    const locPage = await locContext.newPage();
    // Both pages render a "Business" picker (combobox) once the owner list
    // loads; wait on it so the capture shows loaded content, not Skeletons.
    // The accessible name is localized, so match the picker by role only via
    // the business-picker id's label — use the select's own label text.
    const pickerName = { en: "Business", ta: "வணிகம்", hi: "व्यवसाय" }[loc];
    for (const route of ["listings", "products"]) {
      await shot(locPage, `${AGRI}/business/${route}`, `${OUT}/console-${route}-${loc}-1440.png`, 1440, {
        full: true,
        ready: { role: "combobox", name: pickerName },
      });
    }
    await locContext.close();
  }
}

// 3) Kitchen sink: the U2 console section, element-scoped, plus 360 record.
// Non-fatal: the demo page's U1 marquee can keep the viewport "unstable"
// past the element-screenshot timeout on a loaded box; a failure here does
// not invalidate the captured console pages.
{
  const context = await browser.newContext();
  const page = await context.newPage();
  for (const width of [1440, 360]) {
    try {
      await shot(page, `${AGRI}/demo?theme=milk`, `${OUT}/demo-u2-section-${width}.png`, width, {
        element: "U2 · console patterns",
      });
    } catch (err) {
      console.warn(`capture-u2: demo section @${width} skipped — ${err.message.split("\n")[0]}`);
    }
  }
  await context.close();
}

await browser.close();
