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
      command: "pnpm --filter @agri/web-milk dev",
      url: "http://localhost:3000",
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "pnpm --filter @agri/web-organic dev",
      url: "http://localhost:3001",
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
