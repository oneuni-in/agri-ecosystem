import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // scenarios share one backend DB; serialize for determinism
  use: {
    baseURL: "http://localhost:3003",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "pnpm run e2e:api",
      url: "http://127.0.0.1:8000/health",
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
      command: "pnpm --filter @agri/web-milk dev",
      url: "http://localhost:3000",
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
      env: { NEXT_PUBLIC_ENABLE_SW: "1" },
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
