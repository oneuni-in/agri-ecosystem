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
  await page.waitForURL(new RegExp(`^${AGRI}/business`), { timeout: 30_000 });
}

async function shot(page, url, path, width, { full = false, element = null } = {}) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(url, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({ content: "*{animation-play-state:paused!important}" });
  await page.waitForTimeout(600);
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
if (!process.env.DEMO_ONLY) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, VENDOR_PHONE);
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

// 3) Kitchen sink: the U2 console section, element-scoped, plus 360 record.
{
  const context = await browser.newContext();
  const page = await context.newPage();
  await shot(page, `${AGRI}/demo?theme=milk`, `${OUT}/demo-u2-section-1440.png`, 1440, {
    element: "U2 · console patterns",
  });
  await shot(page, `${AGRI}/demo?theme=milk`, `${OUT}/demo-u2-section-360.png`, 360, {
    element: "U2 · console patterns",
  });
  await context.close();
}

await browser.close();
