import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // scenarios share one backend DB; serialize for determinism
  use: {
    baseURL: "http://localhost:3003",
    trace: "retain-on-failure",
  },
  // D29 device matrix. All three projects share the one `webServer` list below
  // - Playwright boots those once for the whole run, not per project.
  projects: [
    // The full suite, exactly as e2e-auth has always run it.
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    // Low-end Android proxy. Only @matrix specs run here: layout, tap targets,
    // locale, a11y and the core journeys are device-sensitive; API-shaped specs
    // (bff-path-traversal, sso) are not, and running them 3x buys nothing.
    { name: "mobile-chrome", use: { ...devices["Pixel 5"] }, grep: /@matrix/ },
    { name: "mobile-safari", use: { ...devices["iPhone 13"] }, grep: /@matrix/ },
  ],
  webServer: [
    {
      command: "pnpm run e2e:api",
      // Probe a peek-ONLY route, not /health. The dev docker stack also serves
      // :8000 but without OTP_TEST_PEEK, so /health could not tell the two
      // apart: reuseExistingServer would silently adopt the peek-less API and
      // every OTP-driven spec then died with "no OTP recorded" - ten opaque
      // failures for one environment mistake (D09's port-8000 trap, D29).
      // A peek-enabled API answers 200 {"code":null} for an unknown phone;
      // one without the flag 404s, so Playwright refuses to reuse it and the
      // resulting port clash names the problem outright.
      url: "http://127.0.0.1:8000/auth/otp/_peek?phone=%2B910000000000",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "pnpm --filter @agri/web-id dev",
      url: "http://localhost:3003",
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      // NEXT_PUBLIC_ENABLE_SW: dev-mode opt-in so the D28 service-worker
      // registration island runs under `next dev` (see sw-register.tsx).
      //
      // NEXT_PUBLIC_VAPID_PUBLIC_KEY: a well-formed but non-functional key, so
      // U1 §10a's price-alert card leaves its feature-dark state and can be
      // asserted. It deliberately does NOT make subscription work — bundled
      // Chromium has no push channel at all, which is why the real
      // subscribe→deliver proof lives in push-verification.spec.ts (owner-run,
      // real Chrome). What this key buys is coverage of the gate: the card
      // appears only when a key is provisioned.
      command: "pnpm --filter @agri/web-milk dev",
      url: "http://localhost:3000",
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
      env: {
        NEXT_PUBLIC_ENABLE_SW: "1",
        NEXT_PUBLIC_VAPID_PUBLIC_KEY:
          process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ??
          "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U",
      },
    },
    {
      command: "pnpm --filter @agri/web-organic dev",
      url: "http://localhost:3001",
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      // D26 vendor console lives in web-agri only (port 3002 per D01-A) -
      // never added when D09/D10 wrote this file since neither spec touched
      // web-agri. Required for e2e/vendor-dashboard.spec.ts.
      command: "pnpm --filter @agri/web-agri dev",
      url: "http://localhost:3002",
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
